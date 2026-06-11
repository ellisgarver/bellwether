"""Institutional, academic, and policy-analytical ingestors.

Covers the eight-dimension basis-set semantic corpus defined in ADR-020
(2026-05-20) — one ingestor per dimension of US macro discourse, no
redundant sources, no pre-clustering topic keyword filter. See
config/whitelist.yaml.

  Basis dimension → ingestor mapping (ADR-020)

    1. US monetary authority           FederalReserveIngestor (fed.py)
    2. US monetary research voice      FedRegionalIngestor (NY, SF, Chicago, Atlanta)
    3. International macro authority   IMFIngestor (curl_cffi + Coveo, ADR-014)
    4. International CB network        BISIngestor (multi-section, ADR-017)
    5. US fiscal authority             CBOIngestor (Wayback bounded-ID enumeration, ADR-023)
                                       CEAIngestor (govinfo ERP, ADR-020)
    6. US financial stability          TreasuryOFRIngestor
    7. US policy think-tank            BrookingsIngestor + PIIEIngestor
    8. Academic primary work           NBERIngestor (direct URL enum, ADR-020)
       Academic-policy column          VoxEUIngestor

  Cross-cutting:
    CongressionalIngestor   Treasury Secretary testimony — distinct Q&A register
                            over dimension 1 + dimension 5 content.

  InstitutionalIngestor   Composite: runs every basis-set ingestor and merges output.

Pre-clustering topic relevance filtering was removed in ADR-020. The basis-set
source selection is the only macro-content scope constraint at ingest time;
JEL classification is applied post-clustering by mnd.clustering.jel_classifier
to label clusters with their primary JEL code, and non-macro clusters
(primary JEL ∉ {E, F, G, H}) are excluded from dynamics analysis only — not
dropped from the embedded corpus.

Removed (ADR-020):
  CFRIngestor — basis-set redundancy with PIIE on the international-policy
                dimension (~80% of CFR output is foreign-policy non-macro,
                and the macro subset overlaps PIIE). Class deleted in the
                second repo cleanse.

Restored (ADR-020):
  NBERIngestor — academic primary-work dimension. Direct URL enumeration
                 of /papers/wNNNNN (no search-API bot wall; citation_*
                 meta tags give clean structured metadata). The original
                 search-API-based ingestor (deleted in ADR-019) is
                 superseded — that path is irrelevant.

Added (ADR-020):
  CEAIngestor — Council of Economic Advisers. govinfo.gov ERP collection
                (Economic Report of the President, 61 packages back to 1947;
                granule-level chapter access with PDF text extraction).

Removed (ADR-012 / MND_PROJECT_SPEC rev3):
  JacksonHoleIngestor — covered by FederalReserveIngestor.
  ArxivIngestor       — 2017-only coverage; removed (code in git history).

Removed (ADR-010):
  AP News, Reuters, MarketWatch journalism tier — removed (code in git history).

All timestamps follow the ADR-008 rule: publication/release date only.
FOMC minutes = release date.
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}


class _WaybackBanned(RuntimeError):
    """Sustained HTTP 429 from Internet Archive replay — a ban, not a blip.

    IA's replay throttle is a *cumulative request-count* cap on the egress IP,
    not a burst limiter: once tripped it stays tripped for the rest of the job
    regardless of pacing (observed 2026-06-09: the CBO walk dies at the same pid
    after ~172 fetches whether spaced 0.3s or 12s, and re-firing escalates the
    ban). Riding it out inside one run is therefore futile and only deepens the
    flag. The CBO fetch loop catches this to PAUSE cleanly — bank the checkpoint
    and exit 0 — so a later run from a fresh egress IP or after a cooldown
    resumes from where it stopped instead of crashing and re-paying from zero.
    """


def _is_retryable(exc: Exception) -> bool:
    """Retry on server errors and transient network failures; not on 4xx."""
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code >= 500
    return True


def _normalize_timeout(kwargs: dict) -> None:
    """In-place: coerce a scalar ``timeout`` kwarg to a (connect, read) tuple.

    A single-float timeout only bounds total time once bytes start flowing; a
    half-open TCP connection (SYN sent, no SYN-ACK) can stall far longer than
    the nominal value. Splitting into (connect, read) — matching ``_get`` and
    ``fed.py`` — caps the connect phase at 10s so a stalled handshake fails
    fast. curl_cffi accepts the same tuple form as ``requests``.
    """
    t = kwargs.get("timeout")
    if isinstance(t, (int, float)):
        kwargs["timeout"] = (10.0, float(t))


def _cffi_get_retry(do_get, url: str):
    """Retry a curl_cffi-style GET on transient failures and return the response.

    The impersonating getters (``_imf_get``/``_atlanta_get``/``_cepr_get``/
    ``_piie_get``) deliberately do NOT call ``raise_for_status`` — callers
    classify the status themselves. That means a 5xx arrives as a normal
    response, not an exception, so ``_get``'s tenacity decorator can't see it.
    This wrapper gives those getters the same transient-failure cushion ``_get``
    has: it retries on network errors and on 429 / 5xx *status codes* with
    exponential backoff, and only returns once the result is non-retryable
    (any <500 status, which the caller then classifies as success vs 4xx-skip)
    or the attempts are exhausted. Without this cushion the fail-loud raises on
    these paths would fire on a single transient blip and nuke a multi-hour
    source; with it, only a *persistent* failure fails the source.

    ``do_get`` is a zero-arg callable performing one GET and returning a
    response. A network exception on the final attempt propagates (systemic);
    a 5xx/429 on the final attempt is returned so the caller's own status
    classification raises with a precise message.
    """
    backoff = 1.0
    for attempt in range(5):
        last = attempt == 4
        try:
            resp = do_get()
        except Exception as exc:
            if last:
                raise
            log.debug("cffi GET %s attempt %d failed: %s", url, attempt + 1, exc)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
            continue
        status = getattr(resp, "status_code", 200)
        if not last and (status == 429 or status >= 500):
            log.debug("cffi GET %s attempt %d → HTTP %d", url, attempt + 1, status)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
            continue
        return resp


@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=1, max=30),
    retry=retry_if_exception(_is_retryable),
)
def _get(url: str, *, timeout=30.0) -> requests.Response:
    # Normalize float timeout to a (connect, read) tuple — see fed.py:_get
    # for the rationale (TCP-level stalls don't trip single-value timeouts).
    if isinstance(timeout, (int, float)):
        timeout = (10.0, float(timeout))
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp


def _extract_body(url: str, *, min_words: int = 50) -> str | None:
    """Fetch URL and extract article text with trafilatura.

    Returns None for a genuine absence (HTTP 4xx) or a real-but-too-short page.
    A transient/systemic fetch failure (HTTP 5xx surviving ``_get``'s retries, a
    connection error, or a timeout) RAISES instead of returning None, so it
    can't masquerade as an empty article and silently under-capture (finding #2).
    """
    try:
        resp = _get(url, timeout=30.0)
    except requests.exceptions.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None and 400 <= status < 500:
            log.debug("Body fetch %s → HTTP %s; genuine absence", url, status)
            return None
        raise
    text = trafilatura.extract(
        resp.text,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    if text and len(text.split()) >= min_words:
        return text
    # Fallback: BeautifulSoup paragraph extraction
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup.find_all(["nav", "footer", "script", "style", "header"]):
        tag.decompose()
    content = soup.find("main") or soup.find("article") or soup.find("body")
    if content:
        text = content.get_text(separator=" ", strip=True)
        if len(text.split()) >= min_words:
            return text
    return None


def _entry_date(entry: feedparser.FeedParserDict) -> date | None:
    """Extract publication date from an RSS entry. Returns None if unparseable."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return date(*val[:3])
            except Exception:
                pass
    return None


def _make_article(
    *,
    source_id: str,
    url: str,
    published_at: str,
    title: str,
    body: str,
    author: str | None = None,
    section: str | None = None,
    tier: int,
    document_type: str,
    extra_meta: dict | None = None,
) -> Article:
    return Article(
        article_id=_stable_article_id(source_id, url),
        source_id=source_id,
        url=url,
        published_at=published_at,
        retrieved_at=_now_utc_iso(),
        title=title,
        body=body,
        author=author,
        section=section,
        language="en",
        tier=tier,
        access="free",
        retrieval="institutional_rss",
        word_count=len(body.split()),
        raw_metadata={"document_type": document_type, **(extra_meta or {})},
    )


_DATE_FMTS = [
    "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%B %d, %Y",
    "%b %d, %Y", "%b. %d, %Y", "%Y/%m/%d", "%m/%d/%Y",
    "%B %Y", "%b %Y",
]


def _parse_date_flexible(text: str) -> date | None:
    """Try common date format strings then regex fallbacks."""
    text = text.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return None


# PIIE publication pages (policy-briefs / working-papers / piie-briefings)
# render the canonical publication date in a dedicated hero-banner block:
#   <div class="hero-banner-publication__date"><time datetime="2009-08-01T...">
# This is the date to trust. ``article:published_time`` on the same pages is
# the 2016-03-02 Drupal-migration timestamp, which trafilatura reads and which
# collapsed the entire pre-2016 back-catalog into 2016 (ADR-029). The sidebar
# "related publications" use ``teaser__date`` <time> elements — explicitly NOT
# matched here so we never pick up a neighbouring paper's date.
_PIIE_PUB_DATE_RE = re.compile(
    r'class="hero-banner-publication__date"[^>]*>\s*<time[^>]*\bdatetime="([^"]+)"',
    re.IGNORECASE,
)


def _piie_publication_date_from_html(html: str) -> date | None:
    """Authoritative publication date for a PIIE publication page.

    Returns ``None`` when the hero-banner date block is absent — the caller
    then drops the record rather than falling back to the unreliable
    ``article:published_time`` migration stamp (see ``_extract_from_html``).
    """
    if not html:
        return None
    m = _PIIE_PUB_DATE_RE.search(html)
    if not m:
        return None
    return _parse_date_flexible(m.group(1)[:10])


# Blog posts render the canonical date in a dedicated Drupal field rather than
# the publication hero-banner's direct <time>: the <time datetime> sits inside
#   <div class="field field--name-field-blog-date ...">...<time datetime="...">
# i.e. one wrapper deeper than publications, so _PIIE_PUB_DATE_RE (which wants
# <time> immediately after the hero block) misses it. Keying on the blog-date
# field is also what lets us drop the CDX enumeration's junk URLs (soft-hyphen-
# mangled slugs, JS placeholder paths, text-fragment links): those resolve live
# to a fallback page with no field-blog-date, so the extractor returns None and
# the caller drops them instead of stamping the 2022-05-18 migration date that
# trafilatura's article:published_time carries on that page (ADR-029).
_PIIE_BLOG_DATE_RE = re.compile(
    r'field--name-field-blog-date\b.*?<time[^>]*\bdatetime="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)


def _piie_blog_date_from_html(html: str) -> date | None:
    """Authoritative publication date for a PIIE blog page.

    Returns ``None`` when the blog-date field is absent (e.g. an enumeration
    junk URL that resolved to a non-article fallback page) so the caller drops
    the record rather than trusting ``article:published_time``.
    """
    if not html:
        return None
    m = _PIIE_BLOG_DATE_RE.search(html)
    if not m:
        return None
    return _parse_date_flexible(m.group(1)[:10])


# CBO runs Drupal with the metatag module, which emits the true publication
# date in structured Dublin Core <meta> tags (dcterms.created / .issued /
# .date). trafilatura *does* read these, but its date picker is order-sensitive
# (verified, trafilatura 1.12.2): when the Open Graph block — which carries
# ``article:published_time`` — appears earlier in <head> than the dcterms
# block (the normal Drupal layout), trafilatura returns the OG value. On CBO
# that OG timestamp is the 2011-12 site-migration stamp, which collapsed the
# pre-migration back-catalogue onto a single 2011 date (same failure class as
# PIIE's 2016 stamp, ADR-029). Reading the dcterms fields *explicitly* is
# therefore authoritative regardless of tag order. We try the genuine
# creation/issue fields in priority order and never fall through to the OG
# stamp: a None result means "no structured date" and the caller drops the
# record (methodology principle 1: never fabricate a date) rather than
# re-admitting the migration timestamp.
_CBO_DATE_META_KEYS = (
    "dcterms.created",
    "dcterms.issued",
    "dcterms.date",
    "dc.date.created",
    "dc.date.issued",
    "dc.date",
)
# Match a <meta> tag carrying one of the keys above in EITHER attribute order
# (name=…/content=… or content=…/name=…), tolerating single/double quotes.
_CBO_META_DATE_RE = re.compile(
    r"<meta\b[^>]*?"
    r"(?:name|property)\s*=\s*['\"](?P<key>[^'\"]+)['\"][^>]*?"
    r"content\s*=\s*['\"](?P<val>[^'\"]+)['\"]"
    r"|<meta\b[^>]*?"
    r"content\s*=\s*['\"](?P<val2>[^'\"]+)['\"][^>]*?"
    r"(?:name|property)\s*=\s*['\"](?P<key2>[^'\"]+)['\"]",
    re.IGNORECASE,
)


def _cbo_publication_date_from_html(html: str) -> date | None:
    """Authoritative CBO publication date from Drupal Dublin Core meta tags.

    Scans for the structured dcterms/dc.date fields and returns the first one
    present in ``_CBO_DATE_META_KEYS`` priority order. Returns ``None`` when no
    such field exists, so the caller drops the record rather than trusting
    trafilatura's order-dependent ``article:published_time`` migration stamp.
    """
    if not html:
        return None
    found: dict[str, str] = {}
    for m in _CBO_META_DATE_RE.finditer(html):
        key = (m.group("key") or m.group("key2") or "").strip().lower()
        val = m.group("val") or m.group("val2")
        if key in _CBO_DATE_META_KEYS and key not in found and val:
            found[key] = val
    for key in _CBO_DATE_META_KEYS:
        if key in found:
            parsed = _parse_date_flexible(found[key][:10])
            if parsed is not None:
                return parsed
    return None


_MONTH_NAME_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}
_QUARTER_MID_MONTH = {"1": 2, "2": 5, "3": 8, "4": 11}
_CHICAGO_FED_MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)
_CHICAGO_FED_QUARTER_RE = re.compile(
    r"\b(?:Q([1-4])|(?:Quarter|Qtr\.?)\s*([1-4]))\b[^\n]{0,30}(\d{4})",
    re.IGNORECASE,
)


def _chicago_fed_date_from_html(html: str, expected_year: int) -> date | None:
    """Read the structured citation block from a Chicago Fed page.

    Chicago Fed publication pages (Chicago Fed Letter, Economic
    Perspectives, Policy Discussion Papers, etc.) render the issue date
    inside dedicated CSS-class spans that trafilatura's main-content
    extractor strips out:

        <span class="cfedArticle__cite__month">September</span>
        <span class="cfedArticle__cite__year">2023</span>

    We read those spans directly via BS4 and synthesize a date with
    day=15 (mid-month). Year must match the URL-derived expected year
    so we don't pick up a citation of someone else's paper. Returns
    None if either span is missing — caller will try the body-text
    fallback.
    """
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None
    month_el = soup.find(class_="cfedArticle__cite__month")
    year_el = soup.find(class_="cfedArticle__cite__year")
    if not (month_el and year_el):
        return None
    month_name = month_el.get_text(strip=True).lower()
    year_text = year_el.get_text(strip=True)
    month = _MONTH_NAME_TO_NUM.get(month_name)
    try:
        year = int(year_text)
    except ValueError:
        return None
    if month is None or year != expected_year:
        return None
    return date(year, month, 15)


def _chicago_fed_date_from_body(body: str, expected_year: int) -> date | None:
    """Extract a publication date from Chicago Fed article body text.

    Used when the structured citation block (handled by
    ``_chicago_fed_date_from_html``) is missing. We scan the body for a
    "MONTH YEAR" or "Q[1-4] YEAR" mention whose year matches the
    URL-derived expected year and synthesize a date with day=15
    (mid-month) or mid-quarter for the SIR weekly aggregation.

    Returns None if no in-year date string is found.
    """
    if not body:
        return None
    head = body[:3000]
    for m in _CHICAGO_FED_MONTH_RE.finditer(head):
        year = int(m.group(2))
        if year != expected_year:
            continue
        month = _MONTH_NAME_TO_NUM[m.group(1).lower()]
        return date(year, month, 15)
    for m in _CHICAGO_FED_QUARTER_RE.finditer(head):
        year = int(m.group(3))
        if year != expected_year:
            continue
        q = m.group(1) or m.group(2)
        month = _QUARTER_MID_MONTH[q]
        return date(year, month, 15)
    return None


def _extract_from_html(
    html: str, *, min_words: int = 30, date_extractor=None,
) -> tuple[str, str, str | None, date | None]:
    """Extract (body_text, title, author, pub_date) from a raw HTML string.

    Body extraction via trafilatura, with a BS4 ``<main>/<article>/<body>``
    fallback when trafilatura returns nothing or a sub-``min_words`` stub.
    Author/date come from trafilatura's metadata extractor.

    ``date_extractor`` (optional ``Callable[[str], date | None]``) is a
    source-specific date reader run against the raw HTML. When provided it
    is AUTHORITATIVE: its result REPLACES trafilatura's metadata date even
    when it returns ``None``. This exists because some CMSes stamp a
    site-migration date into ``article:published_time`` (which trafilatura
    trusts) while the true publication date lives in a structured element —
    e.g. PIIE's 2016 Drupal migration set ``article:published_time`` to
    2016-03-02 on the entire back-catalog, but the real date survives in the
    ``hero-banner-publication__date`` block (see
    ``_piie_publication_date_from_html``). Falling back to the metadata date
    on a None result would silently re-introduce the migration-date bug, so
    we don't — a None here means "no authoritative date", and the caller
    drops the record (methodology principle 1: never fabricate a date).

    Separated from ``_fetch_page_full`` so callers that already hold the
    page HTML (e.g. ``FedRegionalIngestor._fetch_chicago_fed_letter``, which
    re-parses the same HTML for a structured citation block that trafilatura
    strips) don't have to refetch the URL.
    """
    try:
        body = trafilatura.extract(html, include_comments=False, include_tables=False)
        meta = trafilatura.extract_metadata(html)
    except Exception:
        body, meta = None, None
    title = (meta.title or "") if meta else ""
    author = (meta.author or None) if meta else None
    pub_date: date | None = None
    if date_extractor is not None:
        pub_date = date_extractor(html)
    elif meta and meta.date:
        pub_date = _parse_date_flexible(str(meta.date))
    if not body or len(body.split()) < min_words:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["nav", "footer", "script", "style", "header"]):
            tag.decompose()
        content = soup.find("main") or soup.find("article") or soup.find("body")
        if content:
            body = content.get_text(separator=" ", strip=True)
    return (body or ""), title, author, pub_date


def _fetch_page_full(
    url: str, *, min_words: int = 30, getter=None, date_extractor=None,
) -> tuple[str, str, str | None, date | None]:
    """Fetch url; return (body_text, title, author, pub_date). Empty/None on failure.

    ``getter`` defaults to module-level _get (stdlib requests + retries). Pass a
    custom callable for sources behind TLS-fingerprint bot protection (e.g.
    CBO behind DataDome — see CBOIngestor._cbo_get).

    ``date_extractor`` is forwarded to ``_extract_from_html`` as the
    authoritative source-specific date reader (see that docstring).

    Fetch-failure vs. empty-page (the masquerade): a *genuine absence* — HTTP
    4xx (page gone/forbidden) — returns the empty tuple so the caller skips the
    candidate, indistinguishable from a legitimate <min_words drop. But a
    *transient/systemic* failure — HTTP 5xx surviving the getter's retries, or a
    connection/timeout error — RAISES, so it can never masquerade as an empty
    article and silently under-capture (the failure mode the project forbids).
    The retry-decorated ``_get`` already absorbs blips; reaching here means the
    failure persisted, which is the right signal to fail the source loudly.
    """
    fetch = getter if getter is not None else _get
    try:
        resp = fetch(url, timeout=30.0)
    except requests.exceptions.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None and 400 <= status < 500:
            log.debug("Fetch %s → HTTP %s; genuine absence, skipping", url, status)
            return "", "", None, None
        raise
    # Getters behind bot-protection (curl_cffi impersonators) do NOT call
    # raise_for_status — they return the response at any status. Classify it
    # here so a 5xx error page can't be parsed into a short body and dropped
    # as if it were an empty article.
    status = getattr(resp, "status_code", 200)
    if status >= 400:
        if status < 500:
            log.debug("Fetch %s → HTTP %s; genuine absence, skipping", url, status)
            return "", "", None, None
        raise RuntimeError(
            f"Fetch {url} → HTTP {status} (server error; refusing to mask as empty)"
        )
    return _extract_from_html(
        resp.text, min_words=min_words, date_extractor=date_extractor,
    )


def _wp_rest_fetch(
    api_base: str,
    post_type: str,
    start: date,
    end: date,
    *,
    extra_fields: str = "link,date,title,excerpt,content",
) -> Iterator[dict]:
    """Yield raw post dicts from a WordPress REST API for the given date range.

    Pagination is fail-loud. A transient 5xx/429/network error on a page is
    retried with backoff; if it still fails after several attempts the function
    RAISES rather than returning the partial set. The prior behavior — break on
    any exception — let a single transient failure on page 7 of a 500-page
    source silently truncate the tail while the checkpoint still marked the
    sub-ingestor 'completed' (a silent under-capture hole). A genuine
    end-of-list (WordPress returns HTTP 400/404 when paging past the last page)
    ends pagination cleanly. The caller's per-sub-ingestor try/except marks the
    source failed-for-retry on a raise; re-yielded pages are caught by dedup.
    """
    page = 1
    while True:
        params = {
            "per_page": 100,
            "page": page,
            "after": (start - timedelta(days=1)).isoformat() + "T00:00:00Z",
            "before": (end + timedelta(days=1)).isoformat() + "T00:00:00Z",
            "_fields": extra_fields,
        }
        url = f"{api_base}/wp-json/wp/v2/{post_type}"
        resp = None
        last_err: str | None = None
        backoff = 2.0
        for _attempt in range(5):
            try:
                resp = requests.get(
                    url, params=params, headers=_HEADERS, timeout=(10.0, 30.0),
                )
            except Exception as exc:
                last_err = str(exc)
                resp = None
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code in (400, 404):
                return  # genuine end-of-list (paged past last page)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
                resp = None
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code != 200:
                raise RuntimeError(
                    f"WP REST {api_base}/{post_type} page {page}: "
                    f"unexpected HTTP {resp.status_code}"
                )
            break
        if resp is None:
            raise RuntimeError(
                f"WP REST {api_base}/{post_type} page {page} failed after "
                f"5 attempts (last error: {last_err}) — refusing to truncate "
                f"silently"
            )

        posts = resp.json()
        if not isinstance(posts, list) or not posts:
            return
        yield from posts

        total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            return
        page += 1
        time.sleep(0.5)


def _wp_html_to_text(rendered: str) -> str:
    """Strip HTML tags from a WP REST rendered field. Avoids BS4 filename warning on plain text."""
    if not rendered:
        return ""
    if "<" not in rendered:
        return rendered.strip()
    return BeautifulSoup(rendered, "lxml").get_text(strip=True)


def _wp_post_to_article(
    post: dict,
    *,
    source_id: str,
    section: str,
    tier: int,
    document_type: str,
    start: date,
    end: date,
    fetch_full_body: bool = True,
    expected_host: str | None = None,
) -> Article | None:
    """Convert a WP REST API post dict to an Article. Returns None if out of range.

    ``expected_host`` is the WP source's own canonical host (e.g.
    ``www.brookings.edu``). When set, any record whose ``link`` resolves to a
    host outside that source's own domain family is DROPPED before fetching
    (ADR-031 source-identity rule: a syndicated op-ed or a press/media-mention
    is third-party content, not this source's own output). Body-fetch failures
    on the source's own host then always raise (ADR-030: a real outage must
    fail the source, never silently truncate). When unset, no domain filter is
    applied and every fetch failure raises.
    """
    post_date_str = post.get("date", "")
    try:
        pub_date = datetime.fromisoformat(post_date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None
    if pub_date < start or pub_date > end:
        return None

    url = post.get("link", "")
    if not url:
        return None

    # Source-identity rule (ADR-031): each basis-set source contributes only
    # its OWN published content. A WP entry whose canonical link lives off the
    # source's own domain is a syndicated op-ed or a press/media-mention (a
    # scholar's piece republished in the Washington Post, a TV-appearance
    # video, a news-wire write-up) — third-party content that would re-import
    # the journalism dimension removed in ADR-010 and break the independence of
    # the basis-set's source dimensions. Drop it. This is a PROVENANCE filter on
    # source identity, NOT a topical filter, so it stays consistent with
    # ADR-020's no-pre-cluster-topic-gate. Checked BEFORE any body fetch, so an
    # off-domain (often reachable, or paywalled-and-slow) link is never fetched:
    # this also prevents silently keeping the full body of a reachable
    # third-party page, and removes the cross-domain fetch-timeout drag.
    if expected_host:
        link_host = urlparse(url).netloc.lower()
        base_host = expected_host.lower()
        if base_host.startswith("www."):
            base_host = base_host[4:]
        if not (link_host == base_host or link_host.endswith("." + base_host)):
            log.debug("Dropping off-domain WP record %s (not %s)", url, expected_host)
            return None

    title_raw = post.get("title", {})
    title = _wp_html_to_text(
        title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw)
    )

    excerpt_raw = post.get("excerpt", {})
    excerpt = _wp_html_to_text(
        excerpt_raw.get("rendered", "") if isinstance(excerpt_raw, dict) else ""
    )

    # Use content.rendered from API if present (avoids per-article page fetch)
    content_raw = post.get("content", {})
    api_content = _wp_html_to_text(
        content_raw.get("rendered", "") if isinstance(content_raw, dict) else ""
    )

    author: str | None = None
    if api_content and len(api_content.split()) >= 50:
        body = api_content
    elif fetch_full_body:
        # The link is guaranteed on-domain by the source-identity check above,
        # so any body-fetch failure here is a real outage on the source's own
        # host → propagate it (ADR-030 fail-loud), never silently truncate.
        body, fetched_title, author, _ = _fetch_page_full(url, min_words=50)
        if not body or len(body.split()) < 50:
            body = excerpt
        if fetched_title and not title:
            title = fetched_title
    else:
        body = excerpt

    if not body or len(body.split()) < 30:
        return None

    return _make_article(
        source_id=source_id,
        url=url,
        published_at=pub_date.isoformat() + "T00:00:00Z",
        title=title or url,
        body=body,
        author=author,
        section=section,
        tier=tier,
        document_type=document_type,
    )


# ---------------------------------------------------------------------------
# Tier 1 — Institutional policy
# ---------------------------------------------------------------------------


class IMFIngestor(Ingestor):
    """IMF flagship publications (2010-present) via Coveo + curl_cffi.

    Listing source is the public Coveo Search endpoint that powers imf.org's
    own client search bar: ``imfproduction561s308u.org.coveo.com/rest/search/v2``
    with the public Bearer token (harvested from the Next.js chunk
    ``/_next/static/chunks/1166-*.js`` on 2026-05-17). For each series we
    filter by URL prefix + date range and paginate up to Coveo's 1000-result
    cap; over-cap windows recursively bisect the date range.

    Coverage (series_id, URL prefix, document_type):

      | weo   | /en/publications/weo/issues/   | imf_weo            |
      | gfsr  | /en/publications/gfsr/issues/  | imf_gfsr           |
      | fandd | /en/publications/fandd/issues/ | imf_fandd          |
      | wp    | /en/publications/wp/issues/    | imf_working_paper  |
      | blog  | /en/blogs/articles/            | imf_blog           |

    Body extraction tries the Next.js ``_next/data/<buildId>/<path>.json`` SSG
    endpoint first (no HTML parsing), and falls back to trafilatura on the
    HTML page. For flagships (WEO/GFSR) the HTML yields the executive
    summary + chapter intros (~250 words); for blogs and F&D articles it
    yields the full post body (~800 words). buildId is scraped once from
    ``/en/Publications/WEO`` at the start of fetch().

    Network: every imf.org and imfproduction561s308u.org.coveo.com fetch
    goes through ``curl_cffi.requests`` with ``impersonate='chrome131'``.
    Akamai Bot Manager fronts imf.org and 403s stdlib ``requests`` on TLS
    fingerprint regardless of IP or User-Agent (ADR-014, 2026-05-17).
    curl_cffi==0.15.0 is required (see requirements.txt).
    """

    source_id = "imf"

    # imf.org sits behind Akamai (NOT Cloudflare — server: AkamaiGHost).
    # Akamai Bot Manager 403s requests that present only the basic browser UA
    # without the modern client-hint fingerprint (Sec-Fetch-*, Sec-Ch-Ua-*,
    # Upgrade-Insecure-Requests). Sending the full Chrome navigation header
    # set passes the bot filter from residential, mobile, and university IPs
    # (verified 2026-05-17, T-Mobile cellular AS21928). The previous
    # diagnosis of "Cloudflare WAF IP block" in ADR-013 was a misread —
    # this is a header-fingerprint check at Akamai's edge.
    _IMF_HEADERS: dict = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": (
            '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"'
        ),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
    }

    @classmethod
    def _imf_get(cls, url: str, **kwargs):
        """HTTP GET for imf.org URLs, impersonating Chrome's TLS+HTTP/2 fingerprint.

        Akamai Bot Manager 403s stdlib `requests` because urllib3's OpenSSL
        TLS handshake fingerprint (JA3/JA4) doesn't match a real browser, even
        when the HTTP headers do. `curl_cffi` wraps curl-impersonate, which
        replicates Chrome's cipher order, TLS extensions, and HTTP/2 settings
        verbatim. Verified 2026-05-17 (mobile + university IPs both succeed
        with impersonation; both 403 without it).

        Falls back to stdlib `requests` if `curl_cffi` is not installed, which
        will reliably 403 — this is intentional so the failure surfaces loudly
        rather than silently degrading. See ADR-014 / requirements.txt.
        """
        _normalize_timeout(kwargs)
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._IMF_HEADERS)
            return _cffi_get_retry(lambda: cffi_requests.get(url, **kwargs), url)
        except ImportError:
            log.error(
                "curl_cffi not installed; IMF fetches will 403. "
                "Install with `pip install curl_cffi` (see requirements.txt / ADR-014)."
            )
            return _cffi_get_retry(lambda: requests.get(url, **kwargs), url)

    # ------------------------------------------------------------------
    # Coveo Search API — listing path (ADR-014, 2026-05-17)
    # ------------------------------------------------------------------

    # Endpoint, org, and public Bearer token harvested from the imf.org
    # JS bundle at /_next/static/chunks/1166-*.js (search for "COVEO:{").
    # If listing starts returning 401, refetch the chunk and update.
    _COVEO_ENDPOINT = "https://imfproduction561s308u.org.coveo.com/rest/search/v2"
    _COVEO_ORG = "imfproduction561s308u"
    _COVEO_TOKEN = "xx742a6c66-f427-4f5a-ae1e-770dc7264e8a"
    # Coveo v2 caps firstResult+numberOfResults at 1000 without cursor mode.
    # Windows that exceed this bisect on date range.
    _COVEO_MAX_RESULTS = 1000

    # (series_id, URL prefix matched by Coveo @uri, document_type emitted).
    # Order is arbitrary; the composite ingestor doesn't depend on it.
    _COVEO_SERIES: list[tuple[str, str, str]] = [
        ("weo",   "/en/publications/weo/issues/",   "imf_weo"),
        ("gfsr",  "/en/publications/gfsr/issues/",  "imf_gfsr"),
        ("fandd", "/en/publications/fandd/issues/", "imf_fandd"),
        ("wp",    "/en/publications/wp/issues/",    "imf_working_paper"),
        ("blog",  "/en/blogs/articles/",            "imf_blog"),
    ]

    _NEXT_DATA_SCRIPT_RE = re.compile(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
    )

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        build_id = self._fetch_build_id()
        if not build_id:
            log.warning(
                "IMF: could not retrieve a current Next.js buildId; "
                "_next/data SSG body path disabled, trafilatura fallback only"
            )

        for series_id, url_prefix, doc_type in self._COVEO_SERIES:
            log.info(
                "IMF Coveo series=%s window=%s..%s",
                series_id, start.isoformat(), end.isoformat(),
            )
            yielded = 0
            for hit in self._coveo_list(url_prefix, start, end):
                url = hit["url"]
                pub_date = hit["date"]
                title = hit["title"]
                body = self._fetch_publication_body(
                    url, build_id, self._IMF_HEADERS
                )
                if not body or len(body.split()) < 50:
                    continue
                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author="IMF",
                    section=doc_type,
                    tier=1,
                    document_type=doc_type,
                )
                yielded += 1
                time.sleep(0.5)
            log.info("IMF series=%s yielded %d articles", series_id, yielded)

        # Legacy F&D articles (pre-2018) are not in the Coveo prefix index;
        # walk the canonical /external/pubs/ft/fandd/ HTML site directly.
        yield from self._fetch_legacy_fandd(start, end)

    def _fetch_build_id(self) -> str | None:
        try:
            resp = self._imf_get(
                "https://www.imf.org/en/Publications/WEO",
                timeout=30.0,
            )
            if resp.status_code != 200:
                log.warning("IMF buildId fetch HTTP %d", resp.status_code)
                return None
            m = self._NEXT_DATA_SCRIPT_RE.search(resp.text)
            if not m:
                return None
            return (json.loads(m.group(1)) or {}).get("buildId")
        except Exception as exc:
            log.warning("IMF buildId fetch failed: %s", exc)
            return None

    def _coveo_list(
        self, url_prefix: str, start: date, end: date,
    ) -> Iterator[dict]:
        resp = self._coveo_post(url_prefix, start, end, first=0, num=100)
        try:
            j = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"IMF Coveo JSON parse for {url_prefix} [{start}..{end}]: {exc}"
            ) from exc

        total = j.get("totalCount", 0)
        if total == 0:
            return

        if total > self._COVEO_MAX_RESULTS and start < end:
            mid = start + (end - start) // 2
            yield from self._coveo_list(url_prefix, start, mid)
            yield from self._coveo_list(
                url_prefix, mid + timedelta(days=1), end,
            )
            return

        seen: set[str] = set()
        yield from self._coveo_items(j.get("results", []), seen)

        first = 100
        page_size = 100
        while first < min(total, self._COVEO_MAX_RESULTS):
            resp = self._coveo_post(
                url_prefix, start, end, first=first, num=page_size,
            )
            try:
                j = resp.json()
            except Exception as exc:
                raise RuntimeError(
                    f"IMF Coveo page first={first} JSON parse for {url_prefix}: {exc}"
                ) from exc
            results = j.get("results", [])
            if not results:
                break
            yield from self._coveo_items(results, seen)
            first += page_size
            time.sleep(0.3)

    def _coveo_post(
        self, url_prefix: str, start: date, end: date,
        first: int = 0, num: int = 100,
    ):
        aq = (
            f'@uri="{url_prefix}" '
            f'@date>={start.strftime("%Y/%m/%d")} '
            f'@date<={end.strftime("%Y/%m/%d")}'
        )
        body = {
            "q": "",
            "aq": aq,
            "searchHub": "Search",
            "numberOfResults": num,
            "firstResult": first,
            "sortCriteria": "date descending",
            "fieldsToInclude": ["title", "date", "uri", "clickableuri"],
        }
        endpoint = f"{self._COVEO_ENDPOINT}?organizationId={self._COVEO_ORG}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._COVEO_TOKEN}",
            "Accept": "application/json",
            "Origin": "https://www.imf.org",
            "Referer": "https://www.imf.org/",
        }
        try:
            from curl_cffi import requests as cffi_requests

            def _post():
                return cffi_requests.post(
                    endpoint, impersonate="chrome131", json=body,
                    headers=headers, timeout=(10.0, 30.0),
                )
        except ImportError:
            log.error(
                "curl_cffi not installed; Coveo POST will likely 401 / 403. "
                "Install with `pip install curl_cffi==0.15.0` (see requirements.txt)."
            )

            def _post():
                return requests.post(
                    endpoint, json=body, headers=headers, timeout=(10.0, 30.0),
                )

        # Fail-loud retry: a transient 429/5xx/network error is retried with
        # backoff; a non-retryable HTTP status or exhausted retries RAISES so the
        # caller cannot silently truncate a series (the prior code returned the
        # bad response and the caller did `return`/`break`, dropping the tail).
        backoff = 2.0
        last_err: str | None = None
        for _attempt in range(5):
            try:
                resp = _post()
            except Exception as exc:
                last_err = str(exc)
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError(
                f"IMF Coveo POST {url_prefix} [{start}..{end}] first={first}: "
                f"HTTP {resp.status_code}: {resp.text[:300]}"
            )
        raise RuntimeError(
            f"IMF Coveo POST {url_prefix} [{start}..{end}] first={first} failed "
            f"after 5 attempts (last error: {last_err}) — refusing to truncate silently"
        )

    @staticmethod
    def _coveo_items(results: list, seen: set[str]) -> Iterator[dict]:
        """Convert raw Coveo result dicts to ``{url, date, title}``.

        Each item is indexed twice in Coveo: once with an HTTPS URI, once with
        a ``sitecore://`` URI (the master DB record). We keep the HTTPS one and
        rewrite ``origin-www.imf.org`` / ``origin-blogs.imf.org`` to canonical
        ``www.imf.org`` — Coveo indexes the origin hostname but public traffic
        and the Next.js routes use ``www.imf.org``.
        """
        for res in results:
            uri = res.get("uri") or ""
            if not uri.startswith("http"):
                continue
            uri = uri.replace(
                "https://origin-www.imf.org/", "https://www.imf.org/"
            )
            uri = uri.replace(
                "https://origin-blogs.imf.org/", "https://www.imf.org/"
            )
            if uri in seen:
                continue
            seen.add(uri)
            ms = (res.get("raw") or {}).get("date")
            if not ms:
                continue
            try:
                pub_date = datetime.fromtimestamp(
                    ms / 1000, tz=timezone.utc,
                ).date()
            except Exception:
                continue
            title = (res.get("title") or "").strip()
            if not title:
                continue
            yield {"url": uri, "date": pub_date, "title": title}

    # ------------------------------------------------------------------
    # Body extraction
    # ------------------------------------------------------------------

    def _fetch_publication_body(
        self, full_url: str, build_id: str | None, headers: dict,
    ) -> str | None:
        """Resolve body text for an IMF URL.

        Strategy: try the Next.js ``_next/data/<buildId>/<path>.json`` SSG
        endpoint first for ``/en/publications/*`` URLs (no HTML parsing); fall
        back to trafilatura on the rendered HTML. Blog URLs always take the
        trafilatura path because the SSG build does not cover ``/en/blogs/*``.
        """
        if build_id and "imf.org/en/publications/" in full_url.lower():
            path = full_url.split("imf.org", 1)[-1]
            ssg_url = (
                f"https://www.imf.org/_next/data/{build_id}{path}.json"
            )
            try:
                r = self._imf_get(ssg_url, headers=headers, timeout=30.0)
                if r.status_code == 200:
                    try:
                        ssg = r.json()
                        pp = ssg.get("pageProps") or {}
                        for k in ("body", "content", "html", "abstract", "summary"):
                            v = pp.get(k)
                            if isinstance(v, str) and len(v) > 200:
                                text = BeautifulSoup(
                                    v, "lxml",
                                ).get_text(" ", strip=True)
                                if text and len(text.split()) >= 50:
                                    return text
                    except (json.JSONDecodeError, ValueError):
                        pass
            except Exception as exc:
                log.debug("IMF _next/data %s: %s", ssg_url, exc)

        # Authoritative body fetch. _imf_get has already absorbed transient
        # 5xx/429/network via _cffi_get_retry, so classify the FINAL status:
        # 4xx → genuine absence (drop this record); 5xx → systemic, raise so
        # the source fails loud rather than silently shipping a body-less hole.
        resp = self._imf_get(full_url, headers=headers, timeout=30.0)
        status = getattr(resp, "status_code", 200)
        if status >= 400:
            if status < 500:
                return None
            raise RuntimeError(
                f"IMF body fetch {full_url} → HTTP {status} (server error after "
                f"retries; refusing to mask as an empty article)"
            )
        try:
            body = trafilatura.extract(
                resp.text, include_comments=False, include_tables=False,
            )
            if body:
                return body
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup.find_all(
                ["nav", "footer", "script", "style", "header"]
            ):
                tag.decompose()
            content = (
                soup.find("main")
                or soup.find("article")
                or soup.find("body")
            )
            if content:
                return content.get_text(separator=" ", strip=True)
        except Exception as exc:
            log.debug("IMF HTML body parse %s: %s", full_url, exc)
        return None

    # ------------------------------------------------------------------
    # Legacy F&D article-level walker (ADR-014 addendum, 2026-06-05)
    # ------------------------------------------------------------------
    #
    # Coveo indexes pre-2018 Finance & Development ONLY as whole-issue PDFs
    # (en/spa/fre language variants of one /external/pubs/ft/fandd/*.pdf per
    # issue), so the @uri="/en/publications/fandd/issues/" prefix query in
    # _COVEO_SERIES misses every legacy F&D *article*. That produced a 16x
    # cliff at the 2017→2018 boundary (imf_fandd 2017=5 vs 2018=81). The
    # legacy site still serves per-article HTML at the canonical issue path
    # below, so we walk it directly. Article-level granularity is preserved
    # (recovering issue-level PDFs would create a volume discontinuity at the
    # 2017/2018 seam — itself a defect). Bodies must go through _imf_get:
    # plain stdlib requests 403s at Akamai (verified 2026-06-05).

    # Legacy issues live at /external/pubs/ft/fandd/{year}/{mm}/index.htm with
    # relative same-directory article slugs (e.g. blackden.htm). 2018+ F&D is
    # the Next.js /en/publications/fandd/ site handled by the Coveo prefix.
    _LEGACY_FANDD_FIRST_YEAR = 2010
    _LEGACY_FANDD_LAST_YEAR = 2017
    _LEGACY_FANDD_BASE = "https://www.imf.org/external/pubs/ft/fandd"
    # Same-directory .htm hrefs only (no slash → in the issue dir), lowercase
    # slug. Excludes index.htm in the consumer. 404s (nav pages like
    # basics/people/picture) self-skip on fetch.
    _LEGACY_FANDD_SLUG_RE = re.compile(
        r'href="([a-z0-9][a-z0-9_-]*\.htm)"', re.IGNORECASE
    )

    def _fetch_legacy_fandd(self, start: date, end: date) -> Iterator[Article]:
        lo = max(start.year, self._LEGACY_FANDD_FIRST_YEAR)
        hi = min(end.year, self._LEGACY_FANDD_LAST_YEAR)
        if lo > hi:
            return
        seen: set[str] = set()
        yielded = 0
        log.info("IMF legacy F&D walk years=%d..%d", lo, hi)
        for year in range(lo, hi + 1):
            for month in range(1, 13):
                issue_date = date(year, month, 1)
                if issue_date < start or issue_date > end:
                    continue
                issue_dir = f"{self._LEGACY_FANDD_BASE}/{year}/{month:02d}"
                index_url = f"{issue_dir}/index.htm"
                try:
                    resp = self._imf_get(index_url, timeout=30.0)
                except Exception as exc:
                    raise RuntimeError(
                        f"IMF legacy F&D index {index_url} failed after retries — "
                        f"refusing to silently drop a whole issue"
                    ) from exc
                status = getattr(resp, "status_code", 200)
                if status >= 500:
                    raise RuntimeError(
                        f"IMF legacy F&D index {index_url} → HTTP {status} (server "
                        f"error after retries; refusing to silently drop the issue)"
                    )
                if status != 200:
                    # 404 etc. — a month with no published issue; genuine absence.
                    continue
                slugs = {
                    m.group(1).lower()
                    for m in self._LEGACY_FANDD_SLUG_RE.finditer(resp.text)
                    if m.group(1).lower() != "index.htm"
                }
                for slug in sorted(slugs):
                    art_url = f"{issue_dir}/{slug}"
                    if art_url in seen:
                        continue
                    seen.add(art_url)
                    body, title = self._fetch_legacy_fandd_body(art_url)
                    if not body or len(body.split()) < 50:
                        continue
                    yield _make_article(
                        source_id=self.source_id,
                        url=art_url,
                        published_at=issue_date.isoformat() + "T00:00:00Z",
                        title=title or f"Finance & Development {year}/{month:02d}",
                        body=body,
                        author="IMF",
                        section="imf_fandd",
                        tier=1,
                        document_type="imf_fandd",
                    )
                    yielded += 1
                    time.sleep(0.3)
        log.info("IMF legacy F&D yielded %d articles", yielded)

    def _fetch_legacy_fandd_body(self, url: str) -> tuple[str | None, str | None]:
        resp = self._imf_get(url, timeout=30.0)
        status = getattr(resp, "status_code", 200)
        if status >= 500:
            raise RuntimeError(
                f"IMF legacy F&D body {url} → HTTP {status} (server error after "
                f"retries; refusing to mask as an empty article)"
            )
        if status != 200:
            # 404 nav page (basics/people/picture) — genuine absence, self-skip.
            return None, None
        title = None
        soup = BeautifulSoup(resp.text, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        body = trafilatura.extract(
            resp.text, include_comments=False, include_tables=False,
        )
        if body:
            return body, title
        for tag in soup.find_all(["nav", "footer", "script", "style", "header"]):
            tag.decompose()
        content = soup.find("main") or soup.find("article") or soup.find("body")
        if content:
            return content.get_text(separator=" ", strip=True), title
        return None, title


class BISIngestor(Ingestor):
    """BIS publications via year-based XML sitemaps.

    BIS publishes through several series; this ingestor walks
    ``bis.org/sitemap_documents_{year}.xml`` once per year and dispatches
    each URL to its matching series.

    Series captured (each tagged by ``section`` for downstream analysis):
      - ``working_paper``      ``/publ/work\\d+\\.htm``       ~60-80/yr
      - ``quarterly_review``   ``/publ/qtrpdf/r_qt\\d+\\.htm``  ~16-24/yr
                                                              (4 issues × ~5 articles)
      - ``bulletin``           ``/publ/bisbull\\d+\\.htm``    ~10-20/yr (since 2020)
      - ``speech``             ``/review/r\\d+[a-z]?\\.htm``  hundreds/yr — central
                                                              bankers' speeches that
                                                              BIS curates and republishes
      - ``other_publication``  ``/publ/[a-z]+\\d+\\.htm``     residual catch-all

    Prior code matched only the working-paper pattern, capturing ~70/yr while
    the BIS QR + Bulletins + speeches added ~hundreds more per year.

    Pre-2014 the sitemap lists each ``/review/`` speech only as ``…\\.pdf`` (the
    ``.htm`` landing page exists at the same stem but is not in the sitemap), so
    the ``.htm`` speech pattern matched ~0 speeches in 2010-2012 vs ~765 in 2014
    — a flat 10x undercapture of the early years. ``_fetch_year`` now rewrites
    ``/review/rNNN….pdf`` → ``.htm`` before pattern-matching; the ``seen`` set
    collapses the rewritten form against any direct ``.htm`` sibling.
    """

    source_id = "bis"

    _SITEMAP_TMPL = "https://www.bis.org/sitemap_documents_{year}.xml"
    _BASE = "https://www.bis.org"

    # (regex, section_label, document_type) — first match wins, so order matters
    # for ambiguous URLs (working-paper pattern is the most specific; speeches
    # are the broadest catch-all under /review/).
    _URL_PATTERNS: list[tuple[str, str, str]] = [
        (r"/publ/work\d+\.htm$",          "working_paper",     "bis_working_paper"),
        (r"/publ/qtrpdf/r_qt\d+\.htm$",   "quarterly_review",  "bis_quarterly_review"),
        (r"/publ/bisbull\d+\.htm$",       "bulletin",          "bis_bulletin"),
        (r"/review/r\d+[a-z]?\.htm$",     "speech",            "bis_speech"),
        # Catch-all for other /publ/ HTML documents (annual reports, conference
        # proceedings, etc.). Excludes /publ/qtrpdf/ subdirectory which is
        # handled above. Excludes PDF endings.
        (r"/publ/[a-z]+\d+\.htm$",        "other_publication", "bis_publication"),
    ]

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for year in range(start.year, end.year + 1):
            yield from self._fetch_year(year, start, end, seen)

    def _fetch_year(
        self, year: int, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        sitemap_url = self._SITEMAP_TMPL.format(year=year)
        # Fail-loud per-year fetch: retry transient 5xx/429/network errors with
        # backoff, then RAISE rather than silently dropping the whole year (the
        # prior behavior returned on any exception, so one transient failure
        # lost a full year of BIS). A definitive 404 means BIS publishes no
        # sitemap for that year — a legitimate skip, logged at WARNING so a
        # URL-pattern change still surfaces.
        tree = None
        last_err: str | None = None
        backoff = 2.0
        for _attempt in range(5):
            try:
                resp = requests.get(
                    sitemap_url, headers=_HEADERS, timeout=(10.0, 30.0),
                )
            except Exception as exc:
                last_err = str(exc)
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code == 404:
                log.warning(
                    "BIS sitemap %d: 404 — no sitemap for this year (skipping)",
                    year,
                )
                return
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
                time.sleep(backoff)
                backoff *= 2
                continue
            try:
                resp.raise_for_status()
                tree = ET.fromstring(resp.content)
            except Exception as exc:
                last_err = str(exc)
                time.sleep(backoff)
                backoff *= 2
                continue
            break
        if tree is None:
            raise RuntimeError(
                f"BIS sitemap {year} failed after 5 attempts "
                f"(last error: {last_err}) — refusing to drop the year silently"
            )

        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        compiled = [(re.compile(p), s, d) for p, s, d in self._URL_PATTERNS]
        per_section_count: dict[str, int] = {}

        for url_el in tree.findall("s:url", ns):
            loc_el = url_el.find("s:loc", ns)
            mod_el = url_el.find("s:lastmod", ns)
            if loc_el is None:
                continue
            url = loc_el.text or ""

            # Pre-2014 BIS lists only the PDF of each /review/ speech in the
            # sitemap (the .htm landing page exists at the same stem but is not
            # listed); the .htm jumps from ~0 to ~765 at 2014. Rewrite pdf→htm so
            # the speech pattern matches, trafilatura can parse the page, and the
            # seen-set collapses the pdf-form against any direct .htm sibling.
            # Recovers ~900 speeches/yr in 2010-2013 and ~160/yr of pdf-only
            # speeches that persist in later years.
            url = re.sub(r"(/review/r\d+[a-z]?)\.pdf$", r"\1.htm", url)

            section = None
            doc_type = None
            for pat, sec, dt in compiled:
                if pat.search(url):
                    section = sec
                    doc_type = dt
                    break
            if section is None:
                continue

            pub_date: date | None = None
            if mod_el is not None and mod_el.text:
                try:
                    pub_date = date.fromisoformat(mod_el.text[:10])
                except ValueError:
                    pass
            if url in seen:
                continue
            seen.add(url)

            body, title, author, page_date = _fetch_page_full(url, min_words=50)
            # Prefer the page's own metadata date (trafilatura-extracted)
            # when available; sitemap <lastmod> reflects the last index
            # rebuild, not necessarily publication. Drop the record if
            # neither yields a date — no fabricated dates in the corpus.
            authoritative_date = page_date or pub_date
            if authoritative_date is None:
                log.debug(
                    "BIS %d: dropping %s — no authoritative publication date "
                    "(sitemap lastmod and page metadata both empty)",
                    year, url,
                )
                continue
            if authoritative_date < start or authoritative_date > end:
                continue
            if not body or len(body.split()) < 50:
                continue
            pub_date = authoritative_date

            per_section_count[section] = per_section_count.get(section, 0) + 1
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or url.split("/")[-1],
                body=body,
                author=author,
                section=section,
                tier=1,
                document_type=doc_type,
            )
            time.sleep(1.0)

        if per_section_count:
            log.info("BIS %d: %s", year,
                     ", ".join(f"{s}={n}" for s, n in sorted(per_section_count.items())))


class FedRegionalIngestor(Ingestor):
    """Regional Fed publication blogs: archive-based retrieval.

    Sources and retrieval strategies:
      Liberty Street Economics (NY Fed) — WordPress REST API
      FRBSF Economic Letter/Working Papers — sffed_publications WP REST API
      Chicago Fed publications — XML sitemap URL discovery across multiple
        series (chicago-fed-letter, economic-perspectives, working-papers,
        policy-discussion-papers, profitwise, insights)
      Atlanta Fed publications — per-series JSON listing API
        (/api/feed/getFilteredResults) via curl_cffi (atlantafed.org
        bot-protects stdlib `requests`) across working papers, policy hub
        papers, policy hub macroblog, and the macroeconomy hub feed
        (catches Economy Matters articles). Sitemap was retired in the
        2026 site redesign; see _fetch_atlanta docstring for the full
        URL surface and historical-coverage caveats.

    The main FederalReserveIngestor (fed.py) covers Board communications.
    This ingestor captures regional analytical content.
    """

    source_id = "fed_regional"

    # Atlanta Fed listing API endpoint (Sitecore JSS-backed knockout.js feed
    # behind /research-and-data/publications/* landing pages on the 2026 site
    # redesign). Returns JSON of {Title, Url, Date, Teaser, Authors, ...}.
    # Date filters use ISO YYYY-MM-DD on StartDateRange / EndDateRange.
    _ATLANTA_API = "https://www.atlantafed.org/api/feed/getFilteredResults"

    # Per-series (DataSourceId, ContextId, section_label, url_filter_regex).
    # IDs are stable Sitecore item GUIDs scraped from each landing page's
    # hidden form (#filter_feed_<guid>_pageNumber). If the site rotates them
    # the integration test will catch the empty-result regression.
    # url_filter_regex narrows the macroeconomy hub (which mixes Working
    # Papers + macroblog + events + data products) to research articles.
    _ATLANTA_FEEDS: list[tuple[str, str, str, str | None]] = [
        # Working Papers (~145 items, 2019-02 onward)
        (
            "34e83453b5ee407cb4fdd56c6fb51bce",
            "4bf680469cff43b29350606fdd631ece",
            "working_paper",
            r"/research-and-data/publications/working-papers/",
        ),
        # Policy Hub Papers (~69 items, 2020-01 onward)
        (
            "70bd0a45f4fa440b80a5836c8d2b0299",
            "8ed08d49af54420bbeb018041669ff88",
            "policy_hub",
            r"/research-and-data/publications/policy-hub-papers/",
        ),
        # Policy Hub Macroblog (~50 items, 2022-10 onward — historical
        # macroblog pre-2022 was deleted in the site redesign)
        (
            "d6fdcbee94bf47af96d7a79feb7c7d98",
            "ca9e4c68de7744c2b5f91d759ab00947",
            "macroblog",
            r"/research-and-data/publications/policy-hub-macroblog/",
        ),
        # What-We-Study : Macroeconomy hub (~387 items, 2016-09 onward —
        # mixed feed catches Economy Matters articles under
        # /research-and-data/YYYY/.../ that the dedicated feeds miss).
        # URL filter excludes events/data tools/external survey links.
        (
            "d3fce710cd4e4065b7d6943ec8cf2524",
            "89350aa44d804a75af76bfd1137197b1",
            "economy_matters",
            r"^https://www\.atlantafed\.org/research-and-data/\d{4}/\d{2}/\d{2}/",
        ),
    ]

    # ADR-033: pre-2019 Atlanta content (macroblog + working papers) was deleted
    # from the live site in the 2026 redesign, so the listing API can't see it and
    # 2010-2018 is a hard zero. Recover both surfaces from the Internet Archive.
    # The macroblog lived on macroblog.typepad.com for its entire pre-2020 life
    # (the frbatlanta.org/blogs/macroblog/ URLs are post-deletion 404 stubs with
    # NO contemporaneous captures) — so its real archive is the typepad host, where
    # the path carries year/month but no day (date comes from page metadata). The
    # WP HTML landing pages are deleted (404 live) but archived contemporaneously
    # under /research/publications/wp/YYYY/NN.aspx (pre-2016) or .../NN-slug (2016+).
    # Each entry: (cdx_prefixes, post-path regex matched against the host-stripped
    # path, section, document_type, exclusive pub_date cap). Both caps are
    # 2019-01-01 because the live fetch already covers 2019+ — the cap prevents
    # double-capture across the old/new split. CQER data-tool pages and the
    # pre-2010 Economic Review are deliberately not recovered.
    _WB_CDX_API = "https://web.archive.org/cdx/search/cdx"
    _WB_SNAP = "https://web.archive.org/web/{ts}id_/{url}"
    _WB_UA = "Mozilla/5.0 (compatible; MND-academic-research/1.0; +https://web.archive.org)"
    _WB_SPACING_S = 3.0
    _ATLANTA_WAYBACK: list = [
        (
            ["macroblog.typepad.com/macroblog"],
            re.compile(r"^/macroblog/(\d{4})/(\d{2})/(?!index\.html$)[^/]+\.html$"),
            "macroblog",
            "fed_regional_research",
            date(2019, 1, 1),
        ),
        (
            ["frbatlanta.org/research/publications/wp",
             "atlantafed.org/research/publications/wp"],
            re.compile(r"^/research/publications/wp/(\d{4})/\d+[a-z]?(?:-[^/]+)?$"),
            "working_paper",
            "fed_staff_report",
            date(2019, 1, 1),
        ),
    ]

    # atlantafed.org returns 403 to stdlib `requests` from RCC/residential IPs
    # — same TLS-fingerprint class as IMF/CBO. curl_cffi with Chrome
    # impersonation defeats it; falling back to stdlib `requests` is intentional
    # so missing-dependency failures surface loudly.
    _ATLANTA_HEADERS: dict = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }

    @classmethod
    def _atlanta_get(cls, url: str, **kwargs):
        """HTTP GET for atlantafed.org URLs, impersonating Chrome.

        Falls back to stdlib `requests` if curl_cffi is missing (will likely
        403) — intentional so missing-dependency failures surface loudly.
        """
        _normalize_timeout(kwargs)
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._ATLANTA_HEADERS)
            return _cffi_get_retry(lambda: cffi_requests.get(url, **kwargs), url)
        except ImportError:
            log.error(
                "curl_cffi not installed; Atlanta Fed fetches will likely 403. "
                "Install with `pip install curl_cffi` (see requirements.txt)."
            )
            kwargs.setdefault("headers", cls._ATLANTA_HEADERS)
            return _cffi_get_retry(lambda: requests.get(url, **kwargs), url)

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        yield from self._fetch_liberty_street(start, end, seen)
        yield from self._fetch_ny_staff_reports(start, end, seen)
        yield from self._fetch_frbsf(start, end, seen)
        yield from self._fetch_chicago_fed_letter(start, end, seen)
        yield from self._fetch_atlanta(start, end, seen)
        yield from self._fetch_atlanta_wayback(start, end, seen)

    # ------------------------------------------------------------------
    # Liberty Street Economics — WP REST API
    # ------------------------------------------------------------------

    def _fetch_liberty_street(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        base = "https://libertystreeteconomics.newyorkfed.org"
        for post in _wp_rest_fetch(base, "posts", start, end):
            url = post.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            article = _wp_post_to_article(
                post,
                source_id="fed_ny",
                section="liberty_street_economics",
                tier=1,
                document_type="fed_regional_research",
                start=start,
                end=end,
                fetch_full_body=True,
                expected_host=urlparse(base).netloc,
            )
            if article:
                yield article
                time.sleep(0.5)

    # ------------------------------------------------------------------
    # NY Fed Staff Reports — RePEc/IDEAS series fip/fednsr
    # ------------------------------------------------------------------
    #
    # Liberty Street Economics (above) only covers the NY Fed blog, which
    # begins 2011 and excludes the bank's flagship working-paper series.
    # Staff Reports are captured here via RePEc/IDEAS, which enumerates the
    # complete series and — verified live 2026-06-03 — exposes clean
    # citation_* meta tags on each item page, identical in shape to the
    # NBER ingestor (citation_publication_date is YYYY/MM/DD for ~sr659+
    # and YYYY-only before that). The series listing pages give the
    # internal RePEc id for each report, which is required to fetch recent
    # papers (whose RePEc id differs from the SR number). Canonical
    # Article.url is the newyorkfed.org PDF.
    _NYSR_LISTING_TEMPLATE = "https://ideas.repec.org/s/fip/fednsr{page}.html"
    _NYSR_ITEM_TEMPLATE = "https://ideas.repec.org/p/fip/fednsr/{rid}.html"
    _NYSR_PDF_TEMPLATE = (
        "https://www.newyorkfed.org/medialibrary/media/research/"
        "staff_reports/sr{number}.pdf"
    )
    # ~7 listing pages today; buffer so a growing series isn't clipped.
    _NYSR_MAX_LISTING_PAGES = 10
    # Listing entries appear newest-first, grouped under <h3>YYYY</h3>
    # headers; each report row is <B>{number} <A HREF="/p/fip/fednsr/{id}.html">.
    _NYSR_ENTRY_RE = re.compile(
        r'<h3>(\d{4})</h3>|<B>\s*(\d+)\s+<A HREF="/p/fip/fednsr/(\d+)\.html"',
        re.I,
    )
    _NYSR_DATE_RE = re.compile(
        r'name="citation_publication_date"[^>]*?content="(\d{4})(?:/(\d{2})/(\d{2}))?"',
        re.I,
    )
    _NYSR_TITLE_RE = re.compile(
        r'name="citation_title"[^>]*?content="([^"]*)"', re.I,
    )
    _NYSR_AUTHORS_RE = re.compile(
        r'name="citation_authors"[^>]*?content="([^"]*)"', re.I,
    )
    _NYSR_ABSTRACT_RE = re.compile(
        r'name="citation_abstract"[^>]*?content="([^"]*)"', re.I,
    )

    @staticmethod
    def _impute_nysr_date(year: int, number: int, cohort: list[int]) -> date:
        """Impute a within-year date for a year-only Staff Report.

        Pre-~2014 RePEc records carry only the publication year. Staff
        Reports are numbered monotonically through the year, so we place
        each one by its rank among same-year reports rather than piling
        them all onto Jan 1 (which would fabricate a weekly-volume spike).
        Deterministic and independent of any anchor — it is an imputation
        of an unavailable field, not a tuned parameter. Falls back to
        mid-year when the cohort is unknown.
        """
        n = len(cohort)
        if n <= 1 or number not in cohort:
            return date(year, 7, 1)
        rank = cohort.index(number)  # 0-based, ascending → earliest first
        frac = (rank + 0.5) / n
        return date(year, 1, 1) + timedelta(days=int(round(frac * 364)))

    def _fetch_ny_staff_reports(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        # Pass 1: walk the series listing (descending by year) and collect
        # (number, rid, year) for every report whose listing year is in window.
        rows: list[tuple[int, str, int]] = []
        for page_idx in range(self._NYSR_MAX_LISTING_PAGES):
            page = "" if page_idx == 0 else str(page_idx + 1)
            url = self._NYSR_LISTING_TEMPLATE.format(page=page)
            try:
                resp = _get(url, timeout=30.0)
            except requests.exceptions.HTTPError as exc:
                if getattr(exc.response, "status_code", None) == 404:
                    break  # walked past the last listing page (genuine end)
                raise RuntimeError(
                    f"NY Staff Reports listing {url}: HTTP "
                    f"{getattr(exc.response, 'status_code', None)} after retries — "
                    f"refusing to truncate the series silently"
                ) from exc
            except Exception as exc:
                raise RuntimeError(
                    f"NY Staff Reports listing {url} failed after retries: {exc} — "
                    f"refusing to truncate the series silently"
                ) from exc
            current_year: int | None = None
            page_rows = 0
            stop = False
            for m in self._NYSR_ENTRY_RE.finditer(resp.text):
                if m.group(1):
                    current_year = int(m.group(1))
                    continue
                page_rows += 1
                if current_year is None:
                    continue
                if current_year < start.year:
                    stop = True  # descending listing: nothing older is in window
                    continue
                if current_year > end.year:
                    continue
                rows.append((int(m.group(2)), m.group(3), current_year))
            if page_rows == 0 or stop:
                break
            time.sleep(0.5)

        # Cohort index for year-only date imputation (ascending report number).
        cohorts: dict[int, list[int]] = {}
        for number, _rid, year in rows:
            cohorts.setdefault(year, []).append(number)
        for year in cohorts:
            cohorts[year].sort()

        # Pass 2: fetch each item page, parse citation_* meta, emit Article.
        for number, rid, _listing_year in rows:
            item_url = self._NYSR_ITEM_TEMPLATE.format(rid=rid)
            try:
                resp = _get(item_url, timeout=30.0)
            except requests.exceptions.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if status == 404:
                    log.debug("NY Staff Report sr%d (%s): 404, skipping", number, rid)
                    continue
                raise RuntimeError(
                    f"NY Staff Report sr{number} ({item_url}): HTTP {status} after "
                    f"retries — refusing to silently drop the report"
                ) from exc
            except Exception as exc:
                raise RuntimeError(
                    f"NY Staff Report sr{number} ({item_url}) failed after retries: "
                    f"{exc} — refusing to silently drop the report"
                ) from exc
            page_html = resp.text
            m_date = self._NYSR_DATE_RE.search(page_html)
            if not m_date:
                continue
            yr = int(m_date.group(1))
            imputed = False
            if m_date.group(2) and m_date.group(3):
                try:
                    pub_date = date(yr, int(m_date.group(2)), int(m_date.group(3)))
                except ValueError:
                    pub_date = self._impute_nysr_date(yr, number, cohorts.get(yr, []))
                    imputed = True
            else:
                pub_date = self._impute_nysr_date(yr, number, cohorts.get(yr, []))
                imputed = True
            if pub_date < start or pub_date > end:
                continue

            pdf_url = self._NYSR_PDF_TEMPLATE.format(number=number)
            if pdf_url in seen:
                continue
            seen.add(pdf_url)

            def _meta(rx: re.Pattern) -> str:
                m = rx.search(page_html)
                return html.unescape(m.group(1)).strip() if m else ""

            title = _meta(self._NYSR_TITLE_RE)
            author = _meta(self._NYSR_AUTHORS_RE) or None
            abstract = _meta(self._NYSR_ABSTRACT_RE)
            if not abstract:
                try:
                    soup = BeautifulSoup(page_html, "lxml")
                    el = soup.find(id="abstract-body")
                    if el:
                        abstract = el.get_text(" ", strip=True)
                except Exception:
                    pass
            body = f"{title}\n\n{abstract}".strip() if abstract else title
            if not body:
                continue

            yield _make_article(
                source_id="fed_ny",
                url=pdf_url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or f"NY Fed Staff Report {number}",
                body=body,
                author=author,
                section="ny_staff_report",
                tier=1,
                document_type="fed_staff_report",
                extra_meta={
                    "report_number": f"sr{number}",
                    "repec_id": rid,
                    "ideas_url": item_url,
                    "date_imputed": imputed,
                },
            )
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # FRBSF — sffed_publications WP REST API
    # ------------------------------------------------------------------

    def _fetch_frbsf(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        base = "https://www.frbsf.org"
        for post in _wp_rest_fetch(base, "sffed_publications", start, end):
            url = post.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            article = _wp_post_to_article(
                post,
                source_id="fed_sf",
                section="frbsf_economic_letter",
                tier=1,
                document_type="fed_regional_research",
                start=start,
                end=end,
                fetch_full_body=True,
                expected_host=urlparse(base).netloc,
            )
            if article:
                yield article
                time.sleep(0.5)

    # ------------------------------------------------------------------
    # Chicago Fed Letter — sitemap URL discovery
    # ------------------------------------------------------------------

    # Chicago Fed publication URL patterns, each captured as
    # (regex with a year-group, section_label).  The sitemap walk dispatches
    # on the first matching pattern. Prior code matched only
    # `/chicago-fed-letter/YYYY/NNN`, so it captured ~246 records vs. the
    # ~3,000+ available across all series.
    _CHICAGO_URL_PATTERNS: list[tuple[str, str]] = [
        (r"/publications/chicago-fed-letter/(\d{4})/[^/]+$", "chicago_fed_letter"),
        (r"/publications/economic-perspectives/(\d{4})/[^/]+$", "economic_perspectives"),
        (r"/publications/working-papers/(\d{4})/[^/]+$", "working_paper"),
        (r"/publications/policy-discussion-papers/(\d{4})/[^/]+$", "policy_discussion_paper"),
        (r"/publications/public-policy-papers/(\d{4})/[^/]+$", "public_policy_paper"),
        (r"/publications/profitwise-news-and-views/(\d{4})/[^/]+$", "profitwise"),
        # Chicago Fed Insights research blog lives at
        # /publications/chicago-fed-insights/YYYY/slug (verified against the
        # live sitemap 2026-06-11). The prior two patterns pointed at
        # /publications/insights/ and /publications/blogs/chicago-fed-insights/,
        # neither of which exists — they matched zero URLs, so all ~98 Insights
        # posts were silently missed.
        (r"/publications/chicago-fed-insights/(\d{4})/[^/]+$", "insights"),
    ]

    def _fetch_chicago_fed_letter(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Walk chicagofed.org sitemap across all publication series.

        Prior code matched only Chicago Fed Letter URLs and captured ~246
        articles. The full publication catalog (working papers, Economic
        Perspectives, policy discussion papers, etc.) is enumerated by the
        same sitemap; we now dispatch on a list of URL patterns to expand
        coverage to all Chicago Fed publication series.
        """
        sitemap_url = "https://www.chicagofed.org/sitemap.xml"
        try:
            resp = _get(sitemap_url, timeout=30.0)
            tree = ET.fromstring(resp.content)
        except Exception as exc:
            # The sitemap is the sole discovery surface for Chicago Fed; a
            # failure here yields an empty Chicago Fed corpus. Fail loud rather
            # than silently returning nothing.
            raise RuntimeError(
                f"Chicago Fed sitemap {sitemap_url} failed: {exc} — "
                f"refusing to yield an empty Chicago Fed corpus"
            ) from exc

        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        compiled = [(re.compile(p), s) for p, s in self._CHICAGO_URL_PATTERNS]

        for url_el in tree.findall("s:url", ns):
            loc_el = url_el.find("s:loc", ns)
            if loc_el is None:
                continue
            url = loc_el.text or ""
            year = None
            section = None
            for pat, sec in compiled:
                m = pat.search(url)
                if m:
                    try:
                        year = int(m.group(1))
                    except ValueError:
                        year = None
                    section = sec
                    break
            if year is None or section is None:
                continue
            if year < start.year or year > end.year:
                continue
            if url in seen:
                continue
            seen.add(url)

            # Chicago Fed needs both body extraction AND access to the
            # raw HTML for the structured citation block (.cfedArticle__cite__*
            # CSS classes), which trafilatura strips. Fetch once, extract twice.
            try:
                resp = _get(url, timeout=30.0)
            except requests.exceptions.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if status == 404:
                    log.debug("Chicago Fed %s: 404, skipping", url)
                    continue
                raise RuntimeError(
                    f"Chicago Fed {url}: HTTP {status} after retries — "
                    f"refusing to silently drop the page"
                ) from exc
            except Exception as exc:
                raise RuntimeError(
                    f"Chicago Fed {url} failed after retries: {exc} — "
                    f"refusing to silently drop the page"
                ) from exc
            page_html = resp.text
            body, title, author, meta_date = _extract_from_html(
                page_html, min_words=50,
            )
            if not body or len(body.split()) < 50:
                continue

            # Date extraction strategy for Chicago Fed (verified 2026-05-21):
            #   1. Prefer trafilatura's meta_date if it agrees with URL year.
            #      Working papers typically populate this correctly.
            #   2. Else read the structured citation block (Chicago Fed Letter
            #      / Economic Perspectives / etc. render it inside
            #      <span class="cfedArticle__cite__month"> + ".cfedArticle__cite__year">).
            #   3. Else fall back to a body-text "MONTH YYYY" or "QN YYYY"
            #      regex constrained to the URL-derived year.
            #   4. Else drop — no fabricated dates.
            pub_date: date | None = None
            if meta_date is not None and meta_date.year == year:
                pub_date = meta_date
            if pub_date is None:
                pub_date = _chicago_fed_date_from_html(page_html, year)
            if pub_date is None:
                pub_date = _chicago_fed_date_from_body(body, year)
            if pub_date is None:
                log.debug(
                    "Chicago Fed: dropping %s — no authoritative pub date "
                    "(URL year=%d, meta_date=%s)",
                    url, year, meta_date,
                )
                continue

            if pub_date < start or pub_date > end:
                continue

            yield _make_article(
                source_id="fed_chicago",
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or f"Chicago Fed {section.replace('_', ' ').title()} {year}",
                body=body,
                author=author,
                section=section,
                tier=1,
                document_type="fed_regional_research",
            )
            time.sleep(1.0)

    # ------------------------------------------------------------------
    # Atlanta macroblog — RSS (no historical archive accessible)
    # ------------------------------------------------------------------

    def _fetch_atlanta(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Atlanta Fed publications via per-series JSON listing API.

        URL surface (verified 2026-05-20). The 2026 site redesign retired
        the old discovery surface entirely:
          - ``/sitemap.xml`` → 302 to 404 page (gone)
          - ``/blogs/macroblog/rss`` → HTML 404 (gone)
          - ``/research/publications/{wp,policy-hub,...}`` → 404 (gone)
          - ``/blogs/macroblog`` → 404 (gone)
          - ``/economy-matters`` → 302 to ``/what-we-study`` (gone)

        New strategy (per-series listing API, no HTML/sitemap scraping):
        each publication landing page under ``/research-and-data/publications/*``
        is rendered by a Sitecore JSS knockout.js feed that calls
        ``/api/feed/getFilteredResults?DataSourceId=…&ContextId=…&PageSize=…
        &PageNumber=…&StartDateRange=YYYY-MM-DD&EndDateRange=YYYY-MM-DD``
        and returns JSON of ``{Title, Url, Date, Teaser, Authors, …}`` per
        item. We hit this API directly for four series and merge the results:

          1. Working Papers  (``/research-and-data/publications/working-papers/…``)
             – ~145 items, 2019-02 onward
          2. Policy Hub Papers
             (``/research-and-data/publications/policy-hub-papers/…``)
             – ~69 items, 2020-01 onward
          3. Policy Hub Macroblog
             (``/research-and-data/publications/policy-hub-macroblog/…``)
             – ~50 items, 2022-10 onward
          4. What-We-Study : Macroeconomy hub mixed feed
             – ~387 items, 2016-09 onward; URL-filtered to Economy-Matters-
             style ``/research-and-data/YYYY/MM/DD/…`` to catch articles
             the dedicated feeds don't surface.

        Each series' API begins at its inaugural-publication date — the
        listing endpoint returns zero rows for windows that predate the
        series. Working Papers begin 2019-02, Policy Hub Papers 2020-01,
        Policy Hub Macroblog 2022-10, the Macroeconomy hub feed 2016-09.
        Year-shard queries before those start dates yield empty responses
        (logged as INFO by ``_fetch_atlanta``); the basis-set composition
        for those windows is supplied by the other three regional Feds.

        The body fetch goes through ``_atlanta_get`` (curl_cffi Chrome131
        impersonation) because article pages are bot-protected. See
        ``_ATLANTA_FEEDS`` for the (DataSourceId, ContextId, section,
        url_filter_regex) tuples.
        """
        # Window-cap the API query: API ignores StartDateRange in the
        # future, so cap end at today.
        api_start = start.isoformat()
        api_end = min(end, date.today()).isoformat()

        candidates: list[tuple[str, str, date, str]] = []
        # (url, section, pub_date, title)

        for ds_id, ctx_id, section, url_filter in self._ATLANTA_FEEDS:
            url_pat = re.compile(url_filter) if url_filter else None
            page_num = 1
            section_items = 0
            page_zero_status: str | None = None
            while True:
                params = {
                    "DataSourceId": ds_id,
                    "ContextId": ctx_id,
                    "PageSize": "100",
                    "PageNumber": str(page_num),
                    "StartDateRange": api_start,
                    "EndDateRange": api_end,
                }
                # A request/HTTP/parse failure mid-pagination is NOT
                # end-of-pagination — `break`-ing here truncated the section and
                # the all-series total-zero guard below never noticed. Fail loud.
                # Genuine end-of-pagination is an empty body, zero items, or a
                # short page (handled with `break` further down).
                try:
                    resp = self._atlanta_get(
                        self._ATLANTA_API, params=params, timeout=30.0
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"Atlanta API {section} page={page_num} "
                        f"(DataSourceId={ds_id}) request failed: {exc} — "
                        f"refusing to truncate the section silently"
                    ) from exc
                status_code = getattr(resp, "status_code", 200)
                if status_code >= 400:
                    raise RuntimeError(
                        f"Atlanta API {section} page={page_num} HTTP {status_code} "
                        f"(DataSourceId={ds_id}) — refusing to truncate the "
                        f"section silently"
                    )
                text = resp.text or ""
                if not text.strip():
                    # Empty body is end-of-pagination for a real query; on page 1
                    # it means no rows match the window (legitimate when asking
                    # working-papers for a year before the series existed).
                    if page_num == 1:
                        page_zero_status = "empty_response_page_1"
                        log.info(
                            "Atlanta API %s: empty response on page 1 "
                            "(no rows in window %s..%s)",
                            section, api_start, api_end,
                        )
                    break
                try:
                    payload = json.loads(text)
                    items = json.loads(payload.get("FilteredFeedItemsJson") or "[]")
                except Exception as exc:
                    raise RuntimeError(
                        f"Atlanta API {section} page={page_num} JSON parse failed: "
                        f"{exc} — refusing to truncate the section silently"
                    ) from exc

                if not items:
                    if page_num == 1:
                        page_zero_status = "zero_items_page_1"
                        log.info(
                            "Atlanta API %s: zero items on page 1 "
                            "(no rows in window %s..%s)",
                            section, api_start, api_end,
                        )
                    break

                for it in items:
                    url = it.get("Url") or it.get("UrlNoLang") or ""
                    if not url:
                        continue
                    if url_pat and not url_pat.search(url):
                        continue
                    date_raw = it.get("Date") or ""
                    pub_date = _parse_date_flexible(date_raw[:10])
                    if not pub_date or pub_date < start or pub_date > end:
                        continue
                    title = (it.get("Title") or "").strip()
                    candidates.append((url, section, pub_date, title))
                    section_items += 1

                # End of pagination signaled by a short page (less than
                # the requested PageSize of 100). No artificial page cap —
                # the loop is bounded by the date-range filter and the
                # series' true item count.
                if len(items) < 100:
                    break
                page_num += 1
                time.sleep(0.3)
            log.info(
                "Atlanta API %s: %d items collected from %d pages%s",
                section, section_items, page_num,
                f" ({page_zero_status})" if page_zero_status else "",
            )

        if not candidates:
            # Atlanta API yielded nothing across all 4 series — this is
            # only acceptable if every series is genuinely empty for the
            # window. Surface as ERROR so a regression (rotated DataSourceIds,
            # JSS feed signature change) doesn't silently zero out the source.
            log.error(
                "Atlanta Fed: 0 candidates from listing API across all four "
                "series for window %s..%s — listing API contract may have "
                "changed (rotated DataSourceIds, JSS feed signature) or "
                "TLS impersonation is failing. Investigate.",
                api_start, api_end,
            )
            return

        # Deduplicate by URL (the macroeconomy hub overlaps the dedicated
        # working-papers / macroblog feeds).
        unique: dict[str, tuple[str, date, str]] = {}
        for url, section, pub_date, title in candidates:
            if url in unique:
                continue
            unique[url] = (section, pub_date, title)

        for url, (section, pub_date, title) in unique.items():
            if url in seen:
                continue
            seen.add(url)
            # No try/except here: _fetch_page_full returns empty for a genuine
            # 404 (caught by the <50-word drop below) but RAISES on a transient/
            # systemic fetch failure (finding #2). Re-swallowing that raise would
            # silently drop the page — exactly the masquerade we are removing.
            body, fetched_title, author, meta_date = _fetch_page_full(
                url,
                min_words=50,
                getter=lambda u, **kw: self._atlanta_get(u, **kw),
            )
            # Body must come from the article page itself. Listing-API
            # teasers are 1-2 sentence summaries that would feed boilerplate
            # into the embedding step; if the article body extraction failed
            # we drop the record rather than substitute the teaser.
            if not body or len(body.split()) < 50:
                log.debug(
                    "Atlanta Fed %s: dropping — page body extraction "
                    "yielded %d words (<50 floor)",
                    url, len(body.split()) if body else 0,
                )
                continue
            yield _make_article(
                source_id="fed_atlanta",
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or fetched_title or f"Atlanta Fed {section.replace('_', ' ').title()}",
                body=body,
                author=author,
                section=section,
                tier=1,
                document_type="fed_regional_research",
            )
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # Atlanta pre-2019 recovery from the Internet Archive (ADR-033)
    # ------------------------------------------------------------------

    @staticmethod
    def _atlanta_path(url: str) -> str:
        """Reduce a (possibly http/www/:port/.aspx-variant) Atlanta or typepad
        URL to a bare path key, so the same post archived under either legacy
        host or as an .aspx mirror collapses to one entry."""
        u = url.split("?", 1)[0].split("#", 1)[0]
        u = re.sub(
            r"^https?://(www\.)?"
            r"(frbatlanta\.org|atlantafed\.org|macroblog\.typepad\.com)(:\d+)?",
            "",
            u,
        )
        if u.endswith(".aspx"):
            u = u[:-5]
        if u.endswith("/"):
            u = u[:-1]
        return u

    def _atlanta_wayback_get(
        self, url: str, *, max_attempts: int = 8, throttle_waits: int = 8, **kwargs
    ):
        """GET a web.archive.org URL (CDX index or ``id_`` snapshot) for the
        ADR-033 recovery. Tuple timeout; escalating backoff on 5xx / network
        reset; patient ``Retry-After`` cooldown on 429; fail-loud (RAISES) on
        true exhaustion so a sustained outage can't masquerade as an empty page
        (ADR-030). A genuine 4xx is returned for the caller to treat as absence.
        ~340 fetches on a clean IP — no checkpoint/ban apparatus needed."""
        timeout = kwargs.pop("timeout", 60.0)
        if isinstance(timeout, (int, float)):
            timeout = (10, max(30, int(timeout)))
        kwargs.setdefault("headers", {"User-Agent": self._WB_UA})
        backoff = 4.0
        attempt = 0
        throttle = 0
        while True:
            try:
                resp = requests.get(url, timeout=timeout, **kwargs)
            except Exception as exc:
                attempt += 1
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"Atlanta Wayback GET {url} failed after {attempt} "
                        f"attempts (last error: {exc}) — refusing to mask as empty"
                    ) from exc
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff = min(backoff * 2, 120)
                continue
            if resp.status_code == 429:
                throttle += 1
                if throttle > throttle_waits:
                    raise RuntimeError(
                        f"Atlanta Wayback GET {url}: HTTP 429 persisted across "
                        f"{throttle} patient cooldowns — IA hard throttle"
                    )
                ra = resp.headers.get("Retry-After", "")
                wait = float(ra) if ra.isdigit() else 30.0
                log.info("Atlanta Wayback: 429, cooling %.0fs (%d/%d)",
                         wait, throttle, throttle_waits)
                time.sleep(min(wait, 120))
                continue
            if resp.status_code >= 500:
                attempt += 1
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"Atlanta Wayback GET {url} → HTTP {resp.status_code} "
                        f"after {attempt} attempts — refusing to mask as empty"
                    )
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff = min(backoff * 2, 120)
                continue
            return resp

    def _atlanta_cdx_enumerate(
        self, prefixes: list[str], post_re: "re.Pattern"
    ) -> dict[str, tuple[str, date, str]]:
        """Enumerate archived post URLs across ``prefixes`` whose host-stripped
        path matches ``post_re``. Returns {path: (earliest_real_timestamp,
        url_date, original_url)}. We keep the EARLIEST snapshot, not the latest:
        this content was *deleted* in the 2026 redesign, so a late snapshot
        captures the post-deletion 404/redirect stub — the earliest capture is
        when the page was live and complete. The exact ``original_url`` (with its
        :port/.aspx variant) is retained so the snapshot fetch hits the URL that
        was actually archived. (The 29991231 far-future redirect stub is skipped
        outright.) Fail-loud: a CDX HTTP error RAISES rather than yielding a
        partial set (ADR-030)."""
        out: dict[str, tuple[str, date, str]] = {}
        for prefix in prefixes:
            params = {
                "url": prefix,
                "matchType": "prefix",
                "fl": "original,timestamp",
                "filter": ["statuscode:200", "mimetype:text/html"],
                "limit": 200000,
            }
            resp = self._atlanta_wayback_get(
                self._WB_CDX_API, params=params, timeout=120.0
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Atlanta Wayback CDX {prefix}: HTTP {resp.status_code} "
                    "— refusing to proceed with partial enumeration"
                )
            for line in resp.text.splitlines():
                parts = line.split(" ")
                if len(parts) < 2 or not parts[1].isdigit():
                    continue
                original, ts = parts[0], parts[1]
                if ts[:4] == "2999":
                    continue  # far-future redirect stub
                path = self._atlanta_path(original)
                m = post_re.match(path)
                if not m:
                    continue
                g = m.groups()
                try:
                    if len(g) >= 3:
                        url_date = date(int(g[0]), int(g[1]), int(g[2]))
                    elif len(g) == 2:
                        url_date = date(int(g[0]), int(g[1]), 1)
                    else:
                        url_date = date(int(g[0]), 7, 1)
                except ValueError:
                    continue
                if path not in out or ts < out[path][0]:
                    out[path] = (ts, url_date, original)
        return out

    def _fetch_atlanta_wayback(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Recover Atlanta's pre-2019 macroblog + working papers from the
        Internet Archive (ADR-033). The 2026 redesign deleted these from
        atlantafed.org, so the live listing API can't see them and 2010-2018 is
        a hard zero. Each surface is CDX-enumerated, bodies are fetched from the
        raw ``id_`` snapshot, and records are gated on the page date (URL date
        as fallback). The canonical live URL is stored for dedup/provenance."""
        for prefixes, post_re, section, doc_type, date_cap in self._ATLANTA_WAYBACK:
            snaps = self._atlanta_cdx_enumerate(prefixes, post_re)
            if not snaps:
                log.warning(
                    "Atlanta Wayback %s: 0 archived posts enumerated — CDX "
                    "returned nothing for %s (investigate before clearing)",
                    section, ", ".join(prefixes),
                )
                continue
            kept = 0
            for path, (ts, url_date, original) in sorted(snaps.items()):
                # The exact archived URL is both the snapshot target and the
                # provenance/dedup key — the live frbatlanta path is a 404 stub.
                canon_url = original
                if canon_url in seen:
                    continue
                # Provisional gate on the URL date (year/month for macroblog,
                # mid-year for WP); the page metadata refines it after the fetch.
                if url_date < start or url_date > end:
                    continue
                if date_cap is not None and url_date >= date_cap:
                    continue
                snap_url = self._WB_SNAP.format(ts=ts, url=canon_url)
                body, fetched_title, author, meta_date = _fetch_page_full(
                    snap_url,
                    min_words=50,
                    getter=lambda u, **kw: self._atlanta_wayback_get(u, **kw),
                )
                if not body or len(body.split()) < 50:
                    log.debug(
                        "Atlanta Wayback %s: dropping %s — body <50 words",
                        section, canon_url,
                    )
                    continue
                pub_date = meta_date or url_date
                if pub_date < start or pub_date > end:
                    continue
                if date_cap is not None and pub_date >= date_cap:
                    continue
                seen.add(canon_url)
                # The typepad <title> is the masthead ("macroblog"), not the post
                # title — fall back to the URL slug so each post is distinguishable.
                title = fetched_title
                if not title or title.strip().lower() == "macroblog":
                    slug = path.rsplit("/", 1)[-1]
                    if slug.endswith(".html"):
                        slug = slug[:-5]
                    title = slug.replace("-", " ").strip().title() or None
                yield _make_article(
                    source_id="fed_atlanta",
                    url=canon_url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title or f"Atlanta Fed {section.replace('_', ' ').title()}",
                    body=body,
                    author=author,
                    section=section,
                    tier=1,
                    document_type=doc_type,
                )
                kept += 1
                time.sleep(self._WB_SPACING_S)
            log.info(
                "Atlanta Wayback %s: recovered %d articles (%d posts enumerated)",
                section, kept, len(snaps),
            )


class CBOIngestor(Ingestor):
    """Congressional Budget Office publications — via Wayback Machine.

    Why Wayback (and not cbo.gov direct):
      cbo.gov is fronted by DataDome bot protection. The history of attempts:
        - ADR-013/014-era curl_cffi chrome131 impersonation — defeated 2026-05-18
          when DataDome tightened its TLS/header signal (403 from the homepage).
        - ADR-017 Playwright + curl_cffi-with-cookies hybrid — defeated
          2026-05-20: DataDome now detects the headless-Chromium runtime
          fingerprint and serves the JS challenge interstitial without ever
          resolving it (title='cbo.gov', body_len=0 after 20s+). The
          "clearance" cookie Playwright captures is a challenge-stub cookie,
          not real clearance, and DataDome rotates its value on every
          response. curl_cffi requests carrying these cookies all 403.
      govinfo.gov was considered (ADR-020) and rejected: GPO deposit coverage
      is uneven over time (41 records 2010 → 6 records 2024), introducing
      a non-random time-varying filter that defeats the basis-set framing.

    Wayback Machine has no DataDome and serves clean snapshot HTML for
    cbo.gov/publication/* URLs going back to 2010, preserving the basis-set
    "cbo.gov content" choice — we just retrieve it via the archive instead
    of direct.

    Enumeration strategy (ADR-032, 2026-06-10) — authoritative sitemap, NOT
    an id-range guess:
      The publication universe is read from ``cbo.gov/sitemap.xml`` — the
      site's own complete index (~25k publication ids). The prior design
      (ADR-023) guessed the id range from an id↔date anchor table and walked
      a bounded ``/publication/{id}`` span floored at id 40000. That silently
      under-captured: CBO node ids are NOT chronological (pid 22000→2011 sits
      far below pid 41138→2009), so the floor dropped scattered 2010+
      publications. The sitemap has no floor and makes any residual gap
      measurable instead of silent.

      Wayback snapshot timestamps (needed to build the replay URL) still come
      from one CDX query per 100-id block (``matchType=prefix``) over the id
      range the sitemap spans; we aggregate min/max ts per id and KEEP only
      ids the sitemap declares real publications. Sitemap ids with NO archived
      snapshot are logged as a MEASURABLE IA gap (cbo.gov live is
      DataDome-blocked, so they are unrecoverable) — never a silent drop. We
      do NOT ``collapse=urlkey``; the earliest ts feeds a crawl-date pre-filter
      and the latest *real* ts (never the ``29991231`` far-future redirect) is
      the capture we fetch. The authoritative page-date filter (step 3) — not
      the id — decides 2010+ membership.

    Per-record pipeline:
      1. Snapshot fetch: ``web.archive.org/web/{max_ts}id_/{url}`` — the
         LATEST real capture (``id_`` modifier returns the raw archived body,
         no Wayback toolbar rewrite). The latest real capture avoids the
         degraded pre-2013 early-migration stubs the earliest snapshot holds,
         and we use a concrete captured timestamp — never the ``29991231``
         far-future redirect, which non-deterministically resolves to a
         Wayback interstitial dated "today". Falls back to the earliest
         capture only if the latest is unusable. Extraction via
         ``_fetch_page_full`` (trafilatura + BS4).
      2. Authoritative date: read explicitly from the page's Drupal Dublin
         Core meta tags by ``_cbo_publication_date_from_html`` (the
         ``date_extractor``), NOT trafilatura's generic picker — trafilatura
         is order-sensitive and would return the earlier-in-<head> Open Graph
         ``article:published_time``, which on CBO is the 2011-12 migration
         stamp (see that function). The Wayback snapshot timestamp is a CRAWL
         date and is NEVER used as the publication date — only as the
         pre-fetch filter / fetch target.
      3. Strict keep gate: page_date present AND in ``[start, end]`` AND
         body ≥ 50 words AND title is not the "Wayback Machine" interstitial.
         Records failing any are dropped (no fabricated dates, no teaser-only
         bodies).

    Politeness / robustness:
      - BOTH IA-facing phases are paced at ``_REQUEST_SPACING_S`` (the measured
        sustained-safe replay rate): the CDX enumeration sweep AND the per-pid
        snapshot fetches. The enumeration sweep is paced because it alone is
        enough traffic to trip IA's count-in-window ban; an unpaced sweep
        established the ban before the first fetch and killed the walk at pid 1
        (ADR-023, 2026-06-09 correction).
      - The CDX map is cached to disk (window-keyed) so a resume skips the
        sweep entirely — neither re-hammering IA nor re-paying the enumeration.
      - Exponential backoff retry on Wayback 429 / 502 / 503 / 504 — never
        403 (Wayback does not bot-block CDX).

    The canonical ``url`` field on each emitted Article is the cbo.gov
    publication URL, NOT the Wayback wrapper, so downstream dedupe / cluster
    reporting matches the cbo.gov source-set framing.
    """

    source_id = "cbo"

    # Wayback Machine endpoints
    _CDX_API = "https://web.archive.org/cdx/search/cdx"
    # 'id_' modifier returns the raw archived response body, no rewrite/banner
    _SNAP_PREFIX = "https://web.archive.org/web/{ts}id_/{url}"

    # User-Agent for the Wayback request (identifies the academic project)
    _UA = (
        "Mozilla/5.0 (compatible; MacroNarrativeDynamics/0.1; "
        "academic research; via web.archive.org)"
    )

    # CBO's own sitemap is the AUTHORITATIVE publication universe (ADR-032).
    # It returns HTTP 200 even though cbo.gov *publication pages* are
    # DataDome-blocked (403, even via curl_cffi chrome impersonation) — the
    # sitemap path sits outside the bot wall (verified 2026-06-10). We no
    # longer guess the id range from an id↔date anchor table: CBO node ids
    # are NOT chronological (probed 2026-06-10: pid 21000→1981, 22000→2011,
    # 41138→2009, 41479→2011), so NO id floor can separate 2010+ from older
    # — any floor silently drops scattered 2010+ publications, the exact
    # under-capture failure the basis-set framing forbids. We enumerate the
    # full sitemap and let the post-fetch page-date gate decide membership.
    _SITEMAP_INDEX = "https://www.cbo.gov/sitemap.xml"

    # Seconds to sleep between per-publication Wayback fetches. Set to IA's
    # MEASURED sustained-safe replay rate (~1 req/9-12s; probed 2026-06-09).
    # This is the load-bearing knob: IA's replay throttle is a count-in-window
    # ban (~15-30 fast requests → block), and hammering through each cooldown
    # makes the bans ESCALATE until one exceeds the _wayback_get retry budget
    # (this is why three 0.3s-paced runs all died at pub/41672, ~170 pids in).
    # Pacing at the safe rate keeps the rolling-window count under the threshold
    # so the ban never trips; the walk then runs to its 36h walltime and the
    # checkpoint carries the ~45h remainder into a second job (ADR-023 resume).
    _REQUEST_SPACING_S = 12.0

    _PUBLICATION_RE = re.compile(r"/publication/(\d+)\b")

    def __init__(self, checkpoint_path: "Path | None" = None) -> None:
        # Optional per-pid resume checkpoint. The full Wayback walk (~13.6k
        # pids at the measured IA-safe ~1 req/9-12s) exceeds the 36h caslake
        # QOS cap, so CBO must be able to resume across sequential SLURM jobs
        # without re-fetching. The checkpoint is a flat one-pid-per-line file
        # (ext "txt" via run_pipeline's _make_ingestor); each pid is appended
        # only AFTER its article has been yielded and flushed by the caller
        # (ADR-023 resume addendum). When no path is given (the composite
        # InstitutionalIngestor path) the walk is uncheckpointed as before.
        self._checkpoint_path = checkpoint_path
        self._done_pids: set[int] = self._load_checkpoint()

    def _load_checkpoint(self) -> set[int]:
        if not self._checkpoint_path or not self._checkpoint_path.exists():
            return set()
        done: set[int] = set()
        with self._checkpoint_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(int(line))
                except ValueError:
                    continue
        log.info("CBO: resuming — %d pids already done (checkpoint %s)",
                 len(done), self._checkpoint_path)
        return done

    def _mark_done(self, pid: int) -> None:
        if not self._checkpoint_path:
            return
        with self._checkpoint_path.open("a") as fh:
            fh.write(f"{pid}\n")
            fh.flush()
        self._done_pids.add(pid)

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        cdx_map = self._build_or_load_cdx_map(start, end)
        yielded = 0
        skipped_done = 0
        # Ascending pid order so the walk is deterministic and resumable: the
        # checkpoint a prior job wrote names exactly the low-id span already
        # covered, and we pick up at the next unmarked pid.
        for pid in sorted(cdx_map):
            earliest_ts, latest_ts = cdx_map[pid]
            # Resume: a pid already in the checkpoint was fully processed
            # (kept-and-flushed or deliberately dropped) by a prior job —
            # skip without spending a Wayback GET. No-op when uncheckpointed.
            if pid in self._done_pids:
                skipped_done += 1
                continue
            snap_date = self._ts_to_date(earliest_ts)
            # Cheap lower-bound pre-filter ONLY. A snapshot can never predate
            # publication, so an earliest capture before the window start
            # proves the publication is pre-window — skip it. We must NOT
            # impose an upper bound on the snapshot date: CBO's /publication/
            # {id} URLs only came into existence with the 2012 site migration,
            # so the earliest archived capture of a 2010-dated publication is
            # ~2012 (verified: the entire 415xx–428xx band first appears
            # 2012-04+). Crawl date lags publication arbitrarily for migrated
            # content; the authoritative window gate is the post-fetch
            # page_date below. Not marked done: it costs no fetch, so
            # re-evaluating it on a later resume is free.
            if snap_date is not None and snap_date < start:
                continue
            # A sustained IA replay ban (cumulative request cap on the egress
            # IP) raises _WaybackBanned. Riding it out within this run is futile
            # — every subsequent pid would 429 too, and re-hammering escalates
            # the ban. So we PAUSE cleanly: log where we stopped and RETURN from
            # the generator. The current pid is NOT marked done (no _mark_done
            # below the raise), so a later run from a fresh egress IP or after a
            # ~12-24h cooldown resumes from exactly here off the checkpoint,
            # banking all prior progress. A 5xx/network outage still raises and
            # fails loud (ADR-030) — only the ban path pauses.
            try:
                article = self._fetch_and_build(
                    pid, earliest_ts, latest_ts, start, end
                )
            except _WaybackBanned as exc:
                log.warning(
                    "CBO: PAUSED at pub/%d — %s. %d publications captured this "
                    "run, %d skipped (already done). Re-fire the source to "
                    "resume from the checkpoint once the IA ban clears (fresh "
                    "egress IP, or ~12-24h cooldown).",
                    pid, exc, yielded, skipped_done,
                )
                return
            if article is not None:
                yield article
                yielded += 1
            # Mark done only after the `yield` resumes — by then the caller
            # has written and flushed this article to the raw file (or, for a
            # dropped pid, there was nothing to write). The checkpoint
            # therefore never marks a pid done before its record is durable.
            self._mark_done(pid)
        if yielded == 0 and skipped_done == 0:
            log.warning(
                "CBO: 0 publications from Wayback in [%s..%s]. Either the "
                "window has no archived snapshots or Wayback CDX is failing "
                "(check web.archive.org availability).",
                start, end,
            )

    # ------------------------------------------------------------------
    # CDX enumeration map (paced sweep, disk-cached for resume)
    # ------------------------------------------------------------------

    def _build_or_load_cdx_map(
        self, start: date, end: date
    ) -> "dict[int, tuple[str, str]]":
        """The ``{pid: (earliest_ts, latest_ts)}`` map driving the fetch walk.

        Built by ONE paced sweep of the bounded CDX id-block space, then cached
        to disk (window-keyed, beside the checkpoint). This is load-bearing for
        resumability, not a mere speed-up:

          - The 218-block CDX sweep is itself enough Wayback traffic to trip
            Internet Archive's count-in-window replay ban. The prior design
            interleaved the (unpaced, 0.5s) sweep with the snapshot fetches, so
            the sweep established the ban *before* the first snapshot fetch —
            which then died on HTTP 429 at the very first pid (pub/41672),
            never advancing the checkpoint. Every re-fire repeated the full
            unpaced sweep, re-escalating the ban: four jobs, zero progress
            (2026-06-09).
          - So the sweep is now paced at the same ``_REQUEST_SPACING_S`` as the
            fetches (count-based ban → stay below the rolling-window threshold),
            and its result is cached. A resume LOADS the cache and skips the
            sweep entirely, so re-fires neither re-hammer IA with 218 blocks nor
            re-pay the ~44min enumeration — they start fetching immediately from
            the checkpoint.

        Uncheckpointed callers (the composite ``InstitutionalIngestor`` path)
        get the paced sweep but no cache (no path to key it to), preserving the
        original single-shot behavior with the ban-prevention pacing added.
        """
        cached = self._load_cdx_cache()
        if cached is not None:
            log.info(
                "CBO: loaded CDX map from cache (%d pids) — skipping the "
                "enumeration sweep (%s)",
                len(cached), self._cdx_cache_path(),
            )
            return cached
        sitemap_pids = self._fetch_sitemap_pids()
        id_lo, id_hi = min(sitemap_pids), max(sitemap_pids)
        prefixes = list(range(id_lo // 100, id_hi // 100 + 1))
        log.info(
            "CBO: %d publications in cbo.gov sitemap (ids %d..%d); resolving "
            "Wayback snapshots via %d 100-id CDX blocks, paced %.0fs/block",
            len(sitemap_pids), id_lo, id_hi, len(prefixes), self._REQUEST_SPACING_S,
        )
        cdx_map: dict[int, tuple[str, str]] = {}
        for i, prefix in enumerate(prefixes):
            for pid, earliest_ts, latest_ts in self._cdx_block(prefix):
                # Keep only ids the sitemap declares real publications; a CDX
                # prefix query also returns redirects / non-publication nodes.
                if pid in sitemap_pids:
                    cdx_map[pid] = (earliest_ts, latest_ts)
            # Pace the sweep at the safe rate so the enumeration phase never
            # establishes the replay ban that used to kill the first fetch. No
            # trailing sleep after the final block.
            if i < len(prefixes) - 1:
                time.sleep(self._REQUEST_SPACING_S + random.uniform(0, 1.0))
        # Sitemap publications that IA never archived are unrecoverable via
        # Wayback (cbo.gov live is DataDome-blocked). Log as a MEASURABLE gap —
        # the basis-set rule is that under-capture must be visible, not silent.
        missing = sitemap_pids - cdx_map.keys()
        if missing:
            sample = sorted(missing)[:20]
            log.warning(
                "CBO: %d of %d sitemap publications have NO Wayback snapshot "
                "(unrecoverable via the archive; sample ids: %s%s)",
                len(missing), len(sitemap_pids), sample,
                " ..." if len(missing) > len(sample) else "",
            )
        self._write_cdx_cache(cdx_map)
        return cdx_map

    def _fetch_sitemap_pids(self) -> "set[int]":
        """The authoritative publication-id universe from cbo.gov/sitemap.xml.

        The sitemap is a ``<sitemapindex>`` pointing at ``sitemap.xml?page=N``
        sub-sitemaps; each lists ``/publication/{id}`` (and ``/{id}/html``)
        URLs. We union the numeric ids across all sub-sitemaps. Raises if the
        index is unreachable or yields zero ids: enumeration must fail loud,
        never fall back to a guessed range that silently under-captures
        (ADR-032).
        """
        index = self._cbo_get(self._SITEMAP_INDEX)
        sub_urls = [
            loc for loc in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", index)
            if "sitemap.xml?page=" in loc
        ]
        if not sub_urls:
            raise RuntimeError(
                f"CBO: sitemap index {self._SITEMAP_INDEX} returned no "
                f"sub-sitemaps ({len(index)} bytes) — refusing to enumerate "
                "from a guessed id range"
            )
        pids: set[int] = set()
        for sub in sub_urls:
            body = self._cbo_get(sub)
            pids.update(int(m) for m in self._PUBLICATION_RE.findall(body))
        if not pids:
            raise RuntimeError(
                f"CBO: sitemap ({len(sub_urls)} sub-sitemaps) yielded zero "
                "publication ids — refusing to proceed with an empty universe"
            )
        return pids

    @classmethod
    def _cbo_get(cls, url: str, **kwargs) -> str:
        """GET cbo.gov via curl_cffi chrome impersonation; return response text.

        Used ONLY for the sitemap — publication pages are DataDome-blocked and
        come from Wayback instead. The sitemap path serves 200, but a
        datacenter egress IP is best served looking like a real browser, so we
        impersonate Chrome (same rationale as ``_piie_get``). Raises on any
        non-200 so a DataDome block or outage fails loud rather than yielding
        an empty universe.
        """
        _normalize_timeout(kwargs)
        kwargs.setdefault("timeout", (10, 60))
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            resp = _cffi_get_retry(lambda: cffi_requests.get(url, **kwargs), url)
        except ImportError:
            log.error(
                "curl_cffi not installed; CBO sitemap fetch may be blocked. "
                "Install with `pip install curl_cffi==0.15.0` (ADR-014)."
            )
            resp = _cffi_get_retry(
                lambda: requests.get(url, headers={"User-Agent": cls._UA}, **kwargs),
                url,
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"CBO sitemap GET {url}: HTTP {resp.status_code} "
                "(DataDome block or outage) — cannot enumerate"
            )
        return resp.text

    def _cdx_cache_path(self) -> "Path | None":
        """Disk path for the CDX map cache, derived from the checkpoint path.

        ``.cbo_<start>_<end>_checkpoint.txt`` → ``.cbo_<start>_<end>_cdxcache.json``.
        None when uncheckpointed (then there is no cache).
        """
        if not self._checkpoint_path:
            return None
        return self._checkpoint_path.with_name(
            self._checkpoint_path.name.replace("_checkpoint.txt", "_cdxcache.json")
        )

    def _load_cdx_cache(self) -> "dict[int, tuple[str, str]] | None":
        path = self._cdx_cache_path()
        if not path or not path.exists():
            return None
        try:
            with path.open() as fh:
                raw = json.load(fh)
            return {int(k): (v[0], v[1]) for k, v in raw.items()}
        except (json.JSONDecodeError, OSError, KeyError, IndexError, ValueError, TypeError) as exc:
            log.warning(
                "CBO: CDX cache %s unreadable (%s) — re-enumerating", path, exc
            )
            return None

    def _write_cdx_cache(self, cdx_map: "dict[int, tuple[str, str]]") -> None:
        """Persist the CDX map atomically (temp file + rename).

        Written only after the full sweep completed, so a partial/aborted sweep
        never leaves a truncated cache a resume would trust. The rename is
        atomic on POSIX: a kill mid-write leaves either the old cache or none.
        """
        path = self._cdx_cache_path()
        if not path:
            return
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w") as fh:
            json.dump({str(k): [v[0], v[1]] for k, v in cdx_map.items()}, fh)
        tmp.replace(path)
        log.info("CBO: cached CDX map (%d pids) → %s", len(cdx_map), path)

    def _fetch_and_build(
        self, pid: int, earliest_ts: str, latest_ts: str,
        start: date, end: date,
    ) -> "Article | None":
        """Fetch one CBO pid's Wayback capture and build an Article, or None.

        Returns None when the page fails any keep gate (interstitial, no
        page-date, out-of-window, body < 50 words). Propagates whatever
        ``_wayback_get`` raises on sustained ban-exhaustion so the caller can
        fail loud rather than silently truncate the series.
        """
        original_url = f"https://www.cbo.gov/publication/{pid}"
        # Fetch the LATEST *real* capture (max ts from the block query),
        # not the earliest. For pre-~2013 content the earliest capture
        # is a degraded early-migration stub: a truncated body, a junk
        # "CBO" title, and a less-accurate date (e.g. pub/41813
        # earliest=22w/"CBO"/2010-01-01 vs a later capture=162w/
        # real-title/2010-01-14). The page's own metadata carries the
        # true publication date regardless of snapshot age, so a later
        # real capture is strictly higher-fidelity. We use a concrete
        # captured timestamp — NEVER the `29991231` far-future redirect,
        # which resolves non-deterministically to a Wayback interstitial
        # page titled "Wayback Machine" and dated "today", corrupting
        # both the body and the extracted date (and silently dropping or
        # mis-dating real publications). `earliest_ts` is retained as
        # the crawl-date pre-filter above and the fallback below.
        snap_url = self._SNAP_PREFIX.format(ts=latest_ts, url=original_url)
        body, fetched_title, _author, page_date = _fetch_page_full(
            snap_url, min_words=50, getter=self._wayback_get,
            date_extractor=_cbo_publication_date_from_html,
        )
        # Fall back to the earliest capture only if the latest is
        # unusable (page later removed → latest is a 404/redirect stub).
        if not body or page_date is None:
            snap_url = self._SNAP_PREFIX.format(ts=earliest_ts, url=original_url)
            body, fetched_title, _author, page_date = _fetch_page_full(
                snap_url, min_words=50, getter=self._wayback_get,
                date_extractor=_cbo_publication_date_from_html,
            )
        time.sleep(self._REQUEST_SPACING_S)
        # Defensive guard: reject a Wayback interstitial/error page
        # captured as 200. The "Wayback Machine" title is the tell;
        # using a concrete captured ts (not the 2999 redirect) should
        # prevent these, but a soft-404 snapshot could still surface.
        if fetched_title and fetched_title.strip() == "Wayback Machine":
            log.debug("CBO pub/%d: dropped — Wayback interstitial (ts=%s)",
                      pid, latest_ts)
            return None
        # Strict date policy (no Wayback-timestamp fallback): the
        # snapshot timestamp is a crawl date, not the publication
        # date. We emit only records whose own page metadata yields
        # a publication date inside the window.
        if page_date is None:
            log.debug("CBO pub/%d: dropped — no page-extracted date (ts=%s)",
                      pid, latest_ts)
            return None
        if page_date < start or page_date > end:
            log.debug("CBO pub/%d: dropped (page_date=%s out of [%s..%s])",
                      pid, page_date, start, end)
            return None
        if not body or len(body.split()) < 50:
            log.debug("CBO pub/%d: body too short (%d words)",
                      pid, len(body.split()) if body else 0)
            return None
        return _make_article(
            source_id=self.source_id,
            # Canonical cbo.gov URL — NOT the Wayback wrapper. Keeps
            # the source-set framing on cbo.gov even though retrieval
            # went through the archive.
            url=original_url,
            published_at=page_date.isoformat() + "T00:00:00Z",
            title=fetched_title or "CBO publication",
            body=body,
            author="CBO",
            section="cbo_publication",
            tier=1,
            document_type="cbo_publication",
        )

    # ------------------------------------------------------------------
    # Wayback CDX — one query per 100-id block (matchType=prefix)
    # ------------------------------------------------------------------

    # Generous per-block row cap. A 100-id block over 2010-present holds at
    # most a few thousand snapshots (≈2k observed for a dense block); 100k
    # leaves ample headroom. If a block ever returns exactly this many rows
    # it was truncated → we raise rather than silently lose the block's tail.
    _CDX_BLOCK_LIMIT = 100000

    def _cdx_block(
        self, prefix: int, *, max_attempts: int = 7
    ) -> list[tuple[int, str, str]]:
        """Query CDX for cbo.gov/publication/{prefix}* (one 100-id block).

        Returns [(publication_id, earliest_ts, latest_ts), ...] for 5-digit
        ids matching this prefix, one tuple per distinct id. ``matchType=
        prefix`` also matches shorter and longer ids sharing the prefix (e.g.
        prefix 594 → 594, 5940-5949, 59400-59499, 594000+); we keep only the
        5-digit ids and let the caller range-clamp.

        We do NOT ``collapse=urlkey`` (which would keep only the earliest
        snapshot per URL). Instead we fetch every snapshot row and aggregate
        ``min`` (earliest) and ``max`` (latest) timestamp per id — CDX sorts
        ascending by timestamp within a urlkey, so the earliest feeds the
        cheap crawl-date pre-filter and the latest feeds the body fetch. The
        latest *real* capture is used (never the ``29991231`` far-future
        redirect, which non-deterministically resolves to a Wayback
        interstitial page dated "today" and corrupts both body and date).

        Retries with exponential backoff + jitter on 429 / 502 / 503 / 504
        AND on raw network errors (Wayback resets connections under burst —
        ``ConnectionResetError`` is its most common transient failure on a
        long walk). Wayback never 403s CDX. The retry budget (7 attempts,
        5s→320s backoff ≈ 10 min total) is sized to outlast Wayback's
        per-minute rate-limit window so a transient reset clears rather than
        aborting the multi-hour full-history walk. Raises RuntimeError only
        on true exhaustion, so a persistent failure surfaces as a failed
        ingest (checkpoint re-run + dedup) rather than a silent coverage hole.
        """
        params = {
            "url": f"cbo.gov/publication/{prefix}",
            "matchType": "prefix",
            "fl": "original,timestamp",
            "filter": ["statuscode:200", "mimetype:text/html"],
            "limit": self._CDX_BLOCK_LIMIT,
        }
        backoff = 5.0
        last_err: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.get(
                    self._CDX_API,
                    params=params,
                    headers={"User-Agent": self._UA},
                    timeout=(10, 90),
                )
            except Exception as exc:
                last_err = str(exc)
                log.debug("CBO CDX block %d*: %s (attempt %d/%d) — backoff %.1fs",
                          prefix, last_err, attempt, max_attempts, backoff)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff *= 2
                continue
            if resp.status_code == 200:
                raw_lines = [ln for ln in resp.text.strip().split("\n") if ln]
                if len(raw_lines) >= self._CDX_BLOCK_LIMIT:
                    raise RuntimeError(
                        f"CBO CDX block {prefix}*: hit the {self._CDX_BLOCK_LIMIT}-row "
                        "limit — output was truncated and the block's tail would be "
                        "lost. Refusing to proceed with a partial block."
                    )
                earliest: dict[int, str] = {}
                latest: dict[int, str] = {}
                for line in raw_lines:
                    parts = line.split(" ")
                    if len(parts) < 2 or not parts[1].isdigit():
                        continue
                    m = self._PUBLICATION_RE.search(parts[0])
                    if not m:
                        continue
                    pid = int(m.group(1))
                    if pid < 10000 or pid > 99999:
                        continue  # keep only 5-digit publication ids
                    ts = parts[1]
                    if pid not in earliest or ts < earliest[pid]:
                        earliest[pid] = ts
                    if pid not in latest or ts > latest[pid]:
                        latest[pid] = ts
                rows = [(pid, earliest[pid], latest[pid]) for pid in sorted(earliest)]
                log.debug("CBO CDX block %d*: %d ids (%d snapshot rows)",
                          prefix, len(rows), len(raw_lines))
                return rows
            if resp.status_code in (429, 502, 503, 504):
                last_err = f"HTTP {resp.status_code}"
                log.debug("CBO CDX block %d*: %s (attempt %d/%d) — backoff %.1fs",
                          prefix, last_err, attempt, max_attempts, backoff)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff *= 2
                continue
            raise RuntimeError(
                f"CBO CDX block {prefix}*: unexpected HTTP {resp.status_code}"
            )
        raise RuntimeError(
            f"CBO CDX block {prefix}* failed after {max_attempts} attempts "
            f"(last error: {last_err}) — refusing to drop the block silently"
        )

    # ------------------------------------------------------------------
    # Wayback snapshot fetcher (passed to _fetch_page_full as ``getter``)
    # ------------------------------------------------------------------

    def _wayback_get(
        self, url: str, *, max_attempts: int = 10, ban_cooldowns: int = 20, **kwargs
    ):
        """HTTP GET for Wayback snapshot URLs, with the CDX path's retry cushion.

        Tuple timeout per c47fb91: a scalar float only bounds the inter-byte
        read gap; a Wayback edge node dripping bytes never trips a 30s single
        value.

        Two *separate* budgets, because 429 and 5xx are different failures:

        - **5xx / raw network error** = a transient blip on IA's single edge IP
          (``getent`` returns one A record, no pool, no IPv6 — it resets/refuses
          under burst and during recovery). Retried over ``max_attempts`` with
          escalating backoff; a sustained outage RAISES so it can never
          masquerade as an empty page and silently under-capture (ADR-030
          soundness rule — the fail-loud body classification in
          ``_fetch_page_full`` is only sound if one blip can't trip it).

        - **429** = IA's replay throttle, a *rolling-window request count* ban
          (~15-30 fast requests trips it; see ``_REQUEST_SPACING_S``). At the
          12s sustained pace this should never trip on a clean egress IP — but
          if IA hiccups we ride it out PATIENTLY rather than give up: honor
          ``Retry-After`` (IA names its own cooldown) over up to ``ban_cooldowns``
          multi-minute waits and CONTINUE the same request once the window
          clears. Patient cooldowns are what IA asks for and do NOT escalate the
          ban — only the prior *rapid* 10-attempt hammer did (2026-06-09: three
          0.3s runs escalated an IP into a hard ban). Only after the full
          patience budget is exhausted — a genuine hard ban needing a human
          (fresh IP / long cooldown) — do we raise ``_WaybackBanned``, which the
          fetch loop catches to pause-and-resume (bank the checkpoint, exit
          clean) rather than crash. Genuine 4xx (404/403/410) returns for the
          caller to skip as real absence.
        """
        timeout = kwargs.pop("timeout", 60.0)
        if isinstance(timeout, (int, float)):
            timeout = (10, max(30, int(timeout)))
        kwargs.setdefault("headers", {"User-Agent": self._UA})
        backoff = 5.0
        attempt = 0          # transient 5xx / network budget
        throttle_hits = 0    # sustained-429 patience budget
        while True:
            try:
                resp = requests.get(url, timeout=timeout, **kwargs)
            except Exception as exc:
                attempt += 1
                log.debug("CBO Wayback GET %s: %s (attempt %d/%d) — backoff %.1fs",
                          url, exc, attempt, max_attempts, backoff)
                if attempt >= max_attempts:
                    raise
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff = min(backoff * 2, 320.0)
                continue
            if resp.status_code == 429:
                throttle_hits += 1
                if throttle_hits >= ban_cooldowns:
                    raise _WaybackBanned(
                        f"CBO Wayback GET {url}: HTTP 429 persisted across "
                        f"{throttle_hits} patient cooldowns — IA replay ban on "
                        f"this egress IP (needs a fresh IP or a long cooldown)"
                    )
                wait = self._retry_after_seconds(resp, fallback=max(backoff, 60.0))
                log.warning(
                    "CBO Wayback GET %s: HTTP 429 (cooldown %d/%d) — waiting %.0fs "
                    "for IA's rolling-window throttle to clear",
                    url, throttle_hits, ban_cooldowns, wait,
                )
                time.sleep(wait + random.uniform(0, min(wait * 0.25, 30.0)))
                backoff = min(backoff * 2, 320.0)
                continue
            if resp.status_code in (502, 503, 504):
                attempt += 1
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"CBO Wayback GET {url}: HTTP {resp.status_code} after "
                        f"{max_attempts} attempts — refusing to drop the snapshot silently"
                    )
                wait = self._retry_after_seconds(resp, fallback=backoff)
                log.debug("CBO Wayback GET %s: HTTP %s (attempt %d/%d) — wait %.1fs",
                          url, resp.status_code, attempt, max_attempts, wait)
                time.sleep(wait + random.uniform(0, min(wait * 0.25, 30.0)))
                backoff = min(backoff * 2, 320.0)
                continue
            return resp

    @staticmethod
    def _retry_after_seconds(resp, *, fallback: float) -> float:
        """Cooldown to wait on a throttle, honoring a ``Retry-After`` header.

        IA sends ``Retry-After`` as integer seconds on its 429s. Parse that
        (clamped to [fallback, 600] so a tiny or pathological value can neither
        re-hammer nor stall the walk); fall back to the caller's exponential
        backoff when the header is absent or unparseable.
        """
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                return min(max(float(int(ra.strip())), fallback), 600.0)
            except (ValueError, AttributeError):
                pass
        return fallback

    @staticmethod
    def _ts_to_date(ts: str) -> date | None:
        """Convert a Wayback timestamp (YYYYMMDDhhmmss) to a date."""
        try:
            return date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
        except (ValueError, IndexError):
            return None



class TreasuryOFRIngestor(Ingestor):
    """Treasury Office of Financial Research and FSOC publications.

    OFR publishes Annual Reports, Working Papers, and Briefs.
    FSOC publishes Annual Reports.
    Both are static HTML/PDF with no RSS — we fetch known index pages.
    """

    source_id = "treasury_ofr"

    _OFR_WORKING_PAPERS = "https://www.financialresearch.gov/working-papers/"
    _OFR_BRIEFS = "https://www.financialresearch.gov/briefs/"
    # FSOC annual reports: the current index page publishes the most-recent
    # report directly; prior years live on per-year landing pages linked from
    # the archive page. (The /studies-and-reports parent page used previously
    # links neither, which is why FSOC ingested 0 records.)
    _FSOC_ANNUAL_INDEX = "https://home.treasury.gov/policy-issues/financial-markets-financial-institutions-and-fiscal-service/fsoc/studies-and-reports/annual-reports"
    _FSOC_ARCHIVE = "https://home.treasury.gov/policy-issues/financial-markets-financial-institutions-and-fiscal-service/financial-stability-oversight-council/council-work/studies-and-reports/annual-reports/fsoc-annual-reports-archive"
    _FSOC_LANDING_RE = re.compile(r"fsoc-(\d{4})-annual-report")

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        yield from self._scrape_ofr_index(self._OFR_WORKING_PAPERS, "ofr_working_paper", start, end)
        yield from self._scrape_ofr_index(self._OFR_BRIEFS, "ofr_brief", start, end)
        yield from self._scrape_fsoc(start, end)

    # OFR publication URL pattern: /working-papers/YYYY/MM/DD/slug or /briefs/YYYY/MM/DD/slug
    _OFR_DATE_RE = re.compile(r"/(?:working-papers|briefs)/(\d{4})/(\d{2})/(\d{2})/")

    def _scrape_ofr_index(
        self, index_url: str, doc_type: str, start: date, end: date
    ) -> Iterator[Article]:
        try:
            resp = _get(index_url)
        except Exception as exc:
            raise RuntimeError(
                f"OFR index fetch failed {index_url} after retries — "
                f"refusing to yield an empty {doc_type} series silently"
            ) from exc
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            m = self._OFR_DATE_RE.search(href)
            if not m:
                continue
            try:
                pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if pub_date < start or pub_date > end:
                continue
            full_url = urljoin("https://www.financialresearch.gov", href)
            if full_url in seen:
                continue
            seen.add(full_url)
            title = link.get_text(strip=True)
            body = _extract_body(full_url, min_words=50)
            if not body:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=full_url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title or doc_type,
                body=body,
                author="OFR",
                section=doc_type,
                tier=1,
                document_type=doc_type,
            )
            time.sleep(1.0)

    # Section/supplement PDFs that share a report year but are NOT the main
    # report (chart decks, slide decks, executive summaries, glossaries, the
    # 2011 report's per-chapter split, etc.). Matched against the separator-
    # stripped lowercased filename stem.
    _FSOC_NON_REPORT_TOKENS = (
        "chart", "slide", "deck", "summary", "glossary", "abbrev", "recommend",
        "letter", "statement", "contents", "notesonthe", "boxes", "developments",
        "macroeconomic", "emergingthreats", "progress", "listofcharts", "tableof",
        "factsheet",
    )

    @staticmethod
    def _page_pdf_urls(page_url: str) -> list[str]:
        resp = _get(page_url, timeout=30.0)
        soup = BeautifulSoup(resp.text, "lxml")
        return [
            urljoin("https://home.treasury.gov", a["href"])
            for a in soup.find_all("a", href=True)
            if a["href"].lower().endswith(".pdf")
        ]

    @classmethod
    def _annual_years(cls, pdf_urls: list[str]) -> set[int]:
        """Report years for which a main annual-report PDF appears in the list."""
        years: set[int] = set()
        for u in pdf_urls:
            name = u.rsplit("/", 1)[-1]
            if not name.lower().endswith(".pdf"):
                continue
            norm = re.sub(r"[^a-z0-9]", "", name[:-4].lower())
            if "annualreport" not in norm and not norm.startswith("fsocar"):
                continue
            m = re.search(r"(20\d{2})", norm)
            if m:
                years.add(int(m.group(1)))
        return years

    @classmethod
    def _pick_annual_pdf(cls, pdf_urls: list[str], year: int) -> str | None:
        """Choose the single main annual-report PDF for ``year``.

        FSOC filenames are wildly inconsistent across years (``FSOCAR2011.pdf``,
        ``2012-Annual-Report.pdf``, ``FSOC-2013-Annual-Report.pdf``,
        ``FSOC2018AnnualReport.pdf`` …). We normalise the stem and prefer an
        exact canonical match, then fall back to any non-supplement PDF that
        carries the year and reads as an annual report.
        """
        cands: list[tuple[str, str]] = []
        for u in pdf_urls:
            name = u.rsplit("/", 1)[-1]
            if not name.lower().endswith(".pdf"):
                continue
            norm = re.sub(r"[^a-z0-9]", "", name[:-4].lower())
            if str(year) not in norm:
                continue
            if any(tok in norm for tok in cls._FSOC_NON_REPORT_TOKENS):
                continue
            if norm in (f"fsoc{year}annualreport", f"fsocar{year}"):
                return u
            cands.append((u, norm))
        for u, norm in cands:
            if "annualreport" in norm or norm.startswith(f"fsocar{year}"):
                return u
        return cands[0][0] if cands else None

    def _scrape_fsoc(self, start: date, end: date) -> Iterator[Article]:
        """Fetch FSOC annual reports as PDF, extracted to text via pypdf.

        FSOC has published one annual report per year since 2011. Each is a
        structured ~200-page PDF surveying systemic-risk conditions — a major
        data point for the financial-stability dimension of the basis set.
        The most-recent report sits on the current index page; prior years are
        reached through per-year landing pages linked from the archive page.
        pypdf is mandatory.
        """
        seen: set[int] = set()

        # 1. Current index page hosts the most-recent annual report directly.
        try:
            cur_pdfs = self._page_pdf_urls(self._FSOC_ANNUAL_INDEX)
        except Exception as exc:
            raise RuntimeError(
                f"FSOC index fetch failed {self._FSOC_ANNUAL_INDEX} after retries — "
                f"refusing to silently drop the most-recent annual report"
            ) from exc
        for year in sorted(self._annual_years(cur_pdfs)):
            yield from self._emit_fsoc_year(year, cur_pdfs, start, end, seen)

        # 2. Archive lists per-year landing pages for prior years.
        try:
            resp = _get(self._FSOC_ARCHIVE, timeout=30.0)
        except Exception as exc:
            raise RuntimeError(
                f"FSOC archive fetch failed {self._FSOC_ARCHIVE} after retries — "
                f"refusing to silently drop all prior-year reports"
            ) from exc
        soup = BeautifulSoup(resp.text, "lxml")
        landing: dict[int, str] = {}
        for link in soup.find_all("a", href=True):
            m = self._FSOC_LANDING_RE.search(link["href"])
            if m:
                landing.setdefault(
                    int(m.group(1)),
                    urljoin("https://home.treasury.gov", link["href"]),
                )
        for year in sorted(landing):
            if year in seen:
                continue
            pub_date = date(year, 12, 31)
            if pub_date < start or pub_date > end:
                continue
            try:
                pdfs = self._page_pdf_urls(landing[year])
            except Exception as exc:
                raise RuntimeError(
                    f"FSOC {year} landing fetch failed {landing[year]} after retries — "
                    f"refusing to silently drop the {year} annual report"
                ) from exc
            yield from self._emit_fsoc_year(year, pdfs, start, end, seen)

    def _emit_fsoc_year(
        self, year: int, pdf_urls: list[str], start: date, end: date, seen: set[int]
    ) -> Iterator[Article]:
        if year in seen:
            return
        # FSOC reports cover a calendar year; date the record at December 31
        # (the report's reporting period close), matching downstream weekly
        # aggregation's treatment of the report's discursive footprint.
        pub_date = date(year, 12, 31)
        if pub_date < start or pub_date > end:
            return
        pdf_url = self._pick_annual_pdf(pdf_urls, year)
        if not pdf_url:
            log.warning(
                "FSOC %d: no main annual-report PDF among %d links",
                year, len(pdf_urls),
            )
            return
        body = self._extract_pdf_text(pdf_url)
        if not body or len(body.split()) < 500:
            log.warning(
                "FSOC %d: PDF extraction yielded %d words (<500 floor) — "
                "extraction may have failed",
                year, len(body.split()) if body else 0,
            )
            return
        seen.add(year)
        yield _make_article(
            source_id=self.source_id,
            url=pdf_url,
            published_at=pub_date.isoformat() + "T00:00:00Z",
            title=f"FSOC Annual Report {year}",
            body=body,
            author="Financial Stability Oversight Council",
            section="fsoc_annual_report",
            tier=1,
            document_type="fsoc_annual_report",
        )
        time.sleep(1.0)

    @staticmethod
    def _extract_pdf_text(pdf_url: str) -> str:
        """Fetch a PDF and return its full extracted text.

        Raises ImportError if pypdf is unavailable. FSOC publishes ~16
        born-digital text PDFs (one annual report per year); a fetch failure
        (after _get's retries) or a parse failure on one of them is systemic,
        not a transient miss, so we RAISE rather than return "" — silently
        dropping a whole year's report is exactly the under-capture failure
        mode the basis set forbids.
        """
        from pypdf import PdfReader
        from io import BytesIO
        try:
            resp = _get(pdf_url, timeout=120.0)
        except Exception as exc:
            raise RuntimeError(
                f"FSOC PDF fetch {pdf_url} failed after retries — refusing to "
                f"silently drop a whole annual report"
            ) from exc
        try:
            reader = PdfReader(BytesIO(resp.content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(p.strip() for p in pages if p.strip())
        except Exception as exc:
            raise RuntimeError(
                f"FSOC PDF parse {pdf_url} failed — refusing to silently drop "
                f"a whole annual report"
            ) from exc


# ---------------------------------------------------------------------------
# Tier 2 — Academic analytical
# ---------------------------------------------------------------------------


class VoxEUIngestor(Ingestor):
    """VoxEU / CEPR columns: date-filtered archive search, sharded by year.

    Access pattern (verified 2026-05-20)
    ----------------------------------
    Host: ``cepr.org`` is fronted by **Cloudflare**. As of 2026-05-20 every
    request from non-browser TLS clients (stdlib ``requests`` / ``urllib3``,
    plain ``curl``) receives ``HTTP 403`` with ``cf-mitigated: challenge`` —
    the JS-challenge variant of Cloudflare's bot mitigation. Header tweaks
    (User-Agent, ``Sec-CH-UA-*``) do not help; the JA3/JA4 TLS fingerprint
    of OpenSSL is the rejection signal, same root cause as ADR-014 (IMF /
    Akamai). The challenge does not require JS execution if the TLS+HTTP/2
    fingerprint matches a real Chrome — i.e. unlike CBO/DataDome (ADR-017)
    we do NOT need Playwright; ``curl_cffi`` with ``impersonate='chrome131'``
    is sufficient.

    Listing path
    ~~~~~~~~~~~~
    ``GET https://cepr.org/voxeu/search-all-columns`` with query params
    ``date[min]``, ``date[max]`` (YYYY-MM-DD), ``page`` (0-indexed). Returns
    server-rendered HTML; columns are ``<article class="c-card">`` blocks
    with a child ``<a href="/voxeu/columns/...">``, a ``<time datetime="..."`` ,
    and an ``h3``/``.c-card__title``. 12 cards per page; a
    ``a[title="Go to last page"]`` pager link gives the last page index.

    Sharding
    ~~~~~~~~
    The search sorts newest-first; a single 2010-present range produces
    hundreds of pages and times out past ~page 400 (prior bug: silent
    timeout dropped 2010-2018). We shard by calendar year — each year has
    ~250-500 columns → ~30-50 pages, well under the timeout.

    Body fetch
    ~~~~~~~~~~
    Individual column pages at ``/voxeu/columns/<slug>`` are likewise
    behind Cloudflare; ``_fetch_page_full`` is called with the curl_cffi
    getter so body fetches use the same TLS impersonation. trafilatura
    extracts the column body cleanly.

    Failure mode if curl_cffi missing
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    We log an ``error`` and fall back to stdlib ``requests``, which will
    almost always 403 — intentional loud failure rather than silent zero.
    ``curl_cffi==0.15.0`` is in ``requirements.txt`` (pinned for IMF and
    CBO too).

    History
    ~~~~~~~
    - Originally stdlib ``requests`` worked because CEPR was un-protected.
    - 2024 site redesign moved CEPR onto Cloudflare; the protection
      tightened around 2026-05-19/20 to consistently challenge non-browser
      TLS fingerprints. Integration suite caught it the next day with
      VoxEU returning zero records across all year shards.
    """

    source_id = "voxeu"

    _SEARCH_URL = "https://cepr.org/voxeu/search-all-columns"
    _BASE = "https://cepr.org"
    _PAGE_TIMEOUT = 60.0

    # Browser-like headers paired with chrome131 TLS impersonation. The TLS
    # fingerprint is what bypasses Cloudflare; these headers just make the
    # subsequent HTTP/2 exchange look consistent with a Chrome session.
    _CEPR_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": (
            '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"'
        ),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Upgrade-Insecure-Requests": "1",
    }

    @classmethod
    def _cepr_get(cls, url: str, **kwargs):
        """HTTP GET for cepr.org, impersonating Chrome's TLS+HTTP/2 fingerprint.

        Cloudflare's bot mitigation on cepr.org rejects stdlib ``requests``
        by JA3/JA4 TLS fingerprint regardless of headers. ``curl_cffi``
        replicates Chrome's cipher order, TLS extensions, and HTTP/2
        settings, which clears the challenge without needing JS execution.

        Falls back to stdlib ``requests`` if ``curl_cffi`` is not installed,
        which will reliably 403 — intentional so the failure surfaces loudly
        rather than silently degrading. See ADR-014 for the IMF analogue.
        """
        _normalize_timeout(kwargs)
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._CEPR_HEADERS)
            return _cffi_get_retry(lambda: cffi_requests.get(url, **kwargs), url)
        except ImportError:
            log.error(
                "curl_cffi not installed; VoxEU fetches will 403. "
                "Install with `pip install curl_cffi==0.15.0` "
                "(see requirements.txt / ADR-014)."
            )
            return _cffi_get_retry(
                lambda: requests.get(url, headers=cls._CEPR_HEADERS, **kwargs), url
            )

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        years = list(range(start.year, end.year + 1))
        shards_with_yield = 0
        for year in years:
            year_start = max(start, date(year, 1, 1))
            year_end = min(end, date(year, 12, 31))
            if year_start > year_end:
                continue
            yielded_before = len(seen)
            yield from self._fetch_year(year_start, year_end, seen)
            if len(seen) > yielded_before:
                shards_with_yield += 1
        # Across a multi-year window we expect cepr.org to yield columns
        # in at least one shard. Zero shards yielding is an upstream-failure
        # signature (Cloudflare tightened, JSS feed swap, TLS impersonation
        # broken). Raise rather than silently shipping an empty corpus.
        if len(years) >= 1 and shards_with_yield == 0:
            raise RuntimeError(
                f"VoxEU: 0 columns yielded across {len(years)} year shards "
                f"({years[0]}..{years[-1]}). cepr.org is reachable but no shard "
                f"produced any article cards — likely Cloudflare tightening or "
                f"a feed contract change. Investigate before re-ingesting."
            )

    def _fetch_year(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        page = 0
        while True:
            # curl_cffi accepts ``params=`` dict like requests.
            params = {
                "date[min]": start.isoformat(),
                "date[max]": end.isoformat(),
                "page": page,
            }
            try:
                resp = self._cepr_get(
                    self._SEARCH_URL, params=params,
                    timeout=self._PAGE_TIMEOUT,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}")
            except Exception as exc:
                # A page fetch that fails after retries means the shard would
                # be truncated (page 0 → zero records; later page → partial).
                # Fail loud so a regression can't hide behind a multi-year
                # aggregate; under-capture is the failure mode we refuse.
                raise RuntimeError(
                    f"VoxEU shard {start}..{end} page {page} failed after "
                    f"retries — refusing to silently truncate the shard"
                ) from exc

            soup = BeautifulSoup(resp.text, "lxml")
            articles = soup.select("article.c-card")
            if not articles:
                if page == 0:
                    log.info(
                        "VoxEU shard %s..%s page 0: no c-card matches "
                        "(Cloudflare challenge or markup change?)",
                        start, end,
                    )
                return

            if page == 0:
                log.info(
                    "VoxEU shard %s..%s: page 0 returned %d cards",
                    start, end, len(articles),
                )

            for art in articles:
                link = art.find("a", href=True)
                if not link:
                    continue
                href = link["href"]
                url = urljoin(self._BASE, href) if href.startswith("/") else href
                if url in seen:
                    continue
                seen.add(url)

                date_el = art.select_one("time")
                if not date_el:
                    continue
                date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
                pub_date = _parse_date_flexible(date_text)
                if not pub_date or pub_date < start or pub_date > end:
                    continue

                title_el = art.select_one("h3, h2, .c-card__title")
                title = title_el.get_text(strip=True) if title_el else ""

                # ADR-016: no Stage 1 topic filter — content-neutral ingest.
                # Body fetch goes through the same curl_cffi getter — the
                # column detail pages are behind the same Cloudflare layer.
                body, fetched_title, author, _ = _fetch_page_full(
                    url, min_words=50, getter=self._cepr_get,
                )
                if not body or len(body.split()) < 50:
                    continue
                if fetched_title and not title:
                    title = fetched_title

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title or "VoxEU column",
                    body=body,
                    author=author,
                    section="voxeu_column",
                    tier=2,
                    document_type="voxeu_column",
                )
                time.sleep(0.5)

            # Check if there are more pages
            last_link = soup.select_one("a[title='Go to last page'], .pager__item--last a")
            if last_link:
                m = re.search(r"page=(\d+)", last_link.get("href", ""))
                if m and page >= int(m.group(1)):
                    return
            elif len(articles) < 12:
                return  # incomplete page = last page

            page += 1
            time.sleep(1.0)


# ---------------------------------------------------------------------------
# Tier 3 — Policy-journalism bridge
# ---------------------------------------------------------------------------


class BrookingsIngestor(Ingestor):
    """Brookings Institution: WordPress REST API (``article`` post type).

    The ``article`` custom type contains all research publications. 53k+ total
    articles accessible via date-range filter. Individual article pages are
    fetched for full body text.

    ADR-020: ingestion is content-neutral — every Brookings article in the
    date window is yielded, regardless of program (Economic Studies, Foreign
    Policy, Global Economy & Development, Governance Studies, Metropolitan
    Policy). Topical relevance is decided post-clustering by
    ``mnd.clustering.jel_classifier``: clusters whose Brookings content lands
    in non-macro JEL codes (I, J, K, L, R, …) are reported but excluded
    from dynamics analysis only. The section label
    ``brookings_economic_studies`` is a pre-ADR-020 cosmetic identifier
    retained for downstream code that grouped by section; it does NOT
    indicate a pre-clustering filter to that program.
    """

    source_id = "brookings"

    _API_BASE = "https://www.brookings.edu"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for post in _wp_rest_fetch(self._API_BASE, "article", start, end):
            url = post.get("link", "")
            if not url or url in seen:
                continue

            title_raw = post.get("title", {})
            title = _wp_html_to_text(
                title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw)
            )

            # ADR-016: no Stage 1 topic filter — content-neutral ingest.
            seen.add(url)
            article = _wp_post_to_article(
                post,
                source_id=self.source_id,
                section="brookings_economic_studies",
                tier=2,
                document_type="brookings_post",
                start=start,
                end=end,
                fetch_full_body=True,
                expected_host=urlparse(self._API_BASE).netloc,
            )
            if article:
                yield article
                # Brookings is the corpus long-pole (~44k articles, one body
                # fetch each). 1s/article was ~12h of pure sleep; 0.25s is
                # ample politeness for a commercial-grade WP host and keeps
                # the walk inside the SLURM wall-clock budget.
                time.sleep(0.25)


class PIIEIngestor(Ingestor):
    """Peterson Institute for International Economics: sitemap-based discovery.

    Access pattern (verified 2026-05-24)
    ----------------------------------
    Host: ``piie.com`` is fronted by **Cloudflare** with the same JS-challenge
    posture as VoxEU/CEPR (ADR-021) and IMF/Akamai (ADR-014). ``curl_cffi``
    with ``impersonate='chrome131'`` clears the challenge; stdlib ``requests``
    gets HTTP 403 on the JA3/JA4 TLS fingerprint.

    Discovery (ADR-026): **Wayback CDX enumeration ∪ live sitemap walk.**
    PIIE migrated CMS around 2016; pre-2016 publications live at flat-slug
    URLs (``/publications/policy-briefs/2008-oil-price-bubble``) while 2016+
    items use a ``/YYYY/`` segment (``/publications/policy-briefs/2016/...``).
    The Drupal xmlsitemap (``?page=N``) lists ONLY the ``/YYYY/`` URLs plus a
    thin recent slice of blogs — it structurally cannot reach the ~889 legacy
    flat-slug publications or the bulk of the blog history (CDX shows ~1,971
    realtime-blog URLs alone vs ~857 sitemap total). So CDX is now the
    workhorse: one ``collapse=urlkey&filter=statuscode:200`` query per content
    prefix surfaces both URL schemes; the sitemap walk is retained only to
    catch brand-new items Wayback has not yet archived. Both feed one deduped
    candidate set. Flat-slug URLs carry no path year, so every CDX URL is
    fetched-then-date-checked against the window (the page's own publication
    date is authoritative; the slug year is never trusted). Bodies are fetched
    from LIVE piie.com via curl_cffi — the legacy URLs still resolve 200.

    Publication dates (ADR-029): publication pages stamp
    ``article:published_time`` with the 2016-03-02 Drupal-migration timestamp,
    which trafilatura trusts — that silently collapsed the entire pre-2016
    policy-brief / working-paper / piie-briefing back-catalog into 2016. The
    true date survives in the ``hero-banner-publication__date`` block, read by
    ``_piie_publication_date_from_html`` and passed as the authoritative
    ``date_extractor`` for those doc types. Blog pages carry a correct
    ``article:published_time`` and use the default extraction path.

    RealTime blog two-era paths (ADR-029): the blog's new posts moved from the
    legacy ``/blogs/realtime-economic-issues-watch/<slug>`` scheme to
    ``/blogs/realtime-economics/<YYYY>/<slug>`` ~2022, which the prior prefix
    set did not follow — the blog hard-zeroed after 2022. Both prefixes are now
    enumerated and the ~199 posts present under both are collapsed by a
    trailing-slug dedup in ``fetch``.

    Why CDX, not ``?page=N`` listing pagination
    -------------------------------------------
    Listing pagination (the ADR-017 strategy) burns post-window pages per
    section and Cloudflare tightens on deep page=N requests within a session
    (the 2026-05-21 integration test got HTTP 403 on page 3 of working-papers,
    yielding 11 records vs the floor of 15). Sitemap discovery (ADR-021)
    avoided that tripwire but silently capped coverage at the 2016+ window.
    CDX queries hit archive.org (no Cloudflare), return the full historical
    URL set in one request per prefix, and fail loud on outage.

    Failure mode if curl_cffi missing
    ---------------------------------
    Same as ADR-014: we log an ``error`` and fall back to stdlib ``requests``,
    which will reliably 403 — intentional loud failure rather than silent
    zero-yield. ``curl_cffi==0.15.0`` is in ``requirements.txt``.
    """

    source_id = "piie"

    _SITEMAP_URL = "https://www.piie.com/sitemap.xml"
    # Generous backstop on the ?page=N walk; the walk self-terminates at the
    # first 404 long before this. PIIE's full sitemap is well under 100 pages.
    _SITEMAP_MAX_PAGES = 500

    # (regex, doc_type, year_group_index_or_None). When year_group_index is
    # not None, we pre-filter URLs whose URL-encoded year lies outside the
    # requested window — this lets us discard publications without fetching.
    _URL_PATTERNS: list[tuple[str, str, int | None]] = [
        (r"/publications/policy-briefs/(\d{4})/[^/]+$", "policy_brief", 1),
        (r"/publications/working-papers/(\d{4})/[^/]+$", "working_paper", 1),
        (r"/publications/piie-briefings/(\d{4})/[^/]+$", "piie_briefing", 1),
        (r"/blogs/realtime-economics/\d{4}/[^/]+$", "blog_post", None),
        (r"/blogs/realtime-economic-issues-watch/[^/]+$", "blog_post", None),
        (r"/blogs/trade-and-investment-policy-watch/[^/]+$", "blog_post", None),
        (r"/blogs/trade-investment-policy-watch/[^/]+$", "blog_post", None),
        (r"/blogs/china-economic-watch/[^/]+$", "blog_post", None),
    ]

    # Wayback CDX enumeration (ADR-026). One prefix query per content type;
    # collapse=urlkey + statuscode:200 yields the distinct canonical URL set,
    # which includes BOTH the pre-2016 flat-slug URLs (absent from the sitemap)
    # and the 2016+ /YYYY/ URLs. The trade blog appears under two slug eras
    # (with and without "and-") and china-economic-watch is a macro blog the
    # sitemap-era patterns never targeted — all are enumerated here for full
    # capture. Flat-slug URLs carry no path year, so every CDX URL is
    # fetched-then-date-checked against the window (the page date is
    # authoritative; the slug year is not).
    #
    # The RealTime blog lives under TWO path eras: the 2016-vintage flat-slug
    # ``realtime-economic-issues-watch`` (1,972 distinct posts, but new posts
    # stopped landing there ~2022 — the hard-zero blog tail we were missing)
    # and the current ``realtime-economics/{YYYY}/`` scheme (carries the
    # post-2022 posts plus a migrated 2008-2021 back-catalog). ~199 posts
    # exist under both; the trailing-slug dedup in fetch() collapses them.
    # realtime-economics is listed FIRST so its current /YYYY/ canonical URL
    # wins that dedup (more likely to resolve live than the legacy slug).
    _CDX_BASE = "http://web.archive.org/cdx/search/cdx"
    _CDX_PREFIXES: list[tuple[str, str]] = [
        ("publications/policy-briefs", "policy_brief"),
        ("publications/working-papers", "working_paper"),
        ("publications/piie-briefings", "piie_briefing"),
        ("blogs/realtime-economics", "blog_post"),
        ("blogs/realtime-economic-issues-watch", "blog_post"),
        ("blogs/trade-and-investment-policy-watch", "blog_post"),
        ("blogs/trade-investment-policy-watch", "blog_post"),
        ("blogs/china-economic-watch", "blog_post"),
    ]
    _CDX_ASSET_RE = re.compile(
        r"\.(?:js|css|png|jpe?g|gif|json|min|svg|ico|woff2?|ttf|pdf|xml)(?:\?|$)",
        re.IGNORECASE,
    )
    _CDX_YEAR_INDEX_RE = re.compile(r"^20\d{2}$")

    # Same Chrome 131 header set used by VoxEUIngestor — paired with the
    # curl_cffi TLS impersonation, this presents Cloudflare with a
    # complete-Chrome-session fingerprint and clears the challenge.
    _PIIE_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": (
            '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"'
        ),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Upgrade-Insecure-Requests": "1",
    }

    @classmethod
    def _piie_get(cls, url: str, **kwargs):
        """HTTP GET for piie.com, impersonating Chrome's TLS+HTTP/2 fingerprint.

        Cloudflare's bot mitigation on piie.com rejects stdlib ``requests``
        by TLS fingerprint regardless of headers. ``curl_cffi`` replicates
        Chrome's cipher order, TLS extensions, and HTTP/2 settings, which
        clears the challenge without needing JS execution.

        Falls back to stdlib ``requests`` if ``curl_cffi`` is not installed,
        which will reliably 403 — loud failure rather than silent zero-yield.
        See VoxEUIngestor._cepr_get for the equivalent pattern.
        """
        _normalize_timeout(kwargs)
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._PIIE_HEADERS)
            return _cffi_get_retry(lambda: cffi_requests.get(url, **kwargs), url)
        except ImportError:
            log.error(
                "curl_cffi not installed; PIIE fetches will 403. "
                "Install with `pip install curl_cffi==0.15.0` "
                "(see requirements.txt / ADR-014)."
            )
            return _cffi_get_retry(
                lambda: requests.get(url, headers=cls._PIIE_HEADERS, **kwargs), url
            )

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        # Wayback CDX enumeration (full history, both URL schemes) unioned with
        # the live sitemap walk (freshest items not yet archived). CDX is the
        # workhorse — PIIE's Drupal sitemap lists only the 2016+ /YYYY/ URLs and
        # a thin slice of recent blogs (ADR-026); CDX surfaces the pre-2016
        # flat-slug publications and the full blog history the sitemap omits.
        cdx_candidates = self._cdx_enumerate()
        sitemap_candidates = self._discover_sitemap_urls(start, end)

        # Dedup across both sources. CDX candidates are listed first (and
        # realtime-economics precedes realtime-economic-issues-watch within
        # them), so the first-seen URL wins on collision.
        #
        # Publications key on the full canonical path. Blog posts key on the
        # trailing slug alone: the RealTime blog's ~199 migrated posts appear
        # at both /blogs/realtime-economic-issues-watch/<slug> and
        # /blogs/realtime-economics/<YYYY>/<slug>, which a full-path key would
        # treat as distinct and double-count. Blog slugs are long topic
        # phrases, so a cross-blog slug collision is effectively impossible.
        merged: dict[str, tuple[str, str]] = {}
        for url, doc_type in (*cdx_candidates, *sitemap_candidates):
            norm = re.sub(r"^https?://(www\.)?", "", url).rstrip("/").lower()
            if doc_type == "blog_post":
                key = "blog:" + norm.rsplit("/", 1)[-1]
            else:
                key = norm
            merged.setdefault(key, (url.rstrip("/"), doc_type))
        candidates = list(merged.values())
        log.info(
            "PIIE: %d candidate URLs (cdx=%d, sitemap=%d, merged=%d) [%s..%s]",
            len(candidates), len(cdx_candidates), len(sitemap_candidates),
            len(candidates), start, end,
        )

        seen: set[str] = set()
        yielded = 0
        body_failed = 0
        no_date = 0
        out_of_window = 0

        for url, doc_type in candidates:
            if url in seen:
                continue
            seen.add(url)

            # article:published_time is unreliable on PIIE: publications carry
            # the 2016 CMS-migration stamp, and blog pages reached via junk
            # enumeration URLs carry a 2022-05-18 fallback stamp. Read the page
            # template's authoritative date element per doc type instead, and
            # drop when it is absent (ADR-029).
            if doc_type in ("policy_brief", "working_paper", "piie_briefing"):
                date_extractor = _piie_publication_date_from_html
            elif doc_type == "blog_post":
                date_extractor = _piie_blog_date_from_html
            else:
                date_extractor = None
            body, fetched_title, author, page_date = _fetch_page_full(
                url, min_words=50, getter=self._piie_get,
                date_extractor=date_extractor,
            )
            if not body or len(body.split()) < 50:
                body_failed += 1
                log.debug("PIIE %s: body unavailable / too short", url)
                continue

            # Methodology principle 1: drop records without an authoritative
            # publication date rather than fabricating one from URL year.
            if page_date is None:
                no_date += 1
                log.debug("PIIE %s: no page-extracted publication date", url)
                continue
            if page_date < start or page_date > end:
                out_of_window += 1
                continue

            title = fetched_title or url.rstrip("/").split("/")[-1].replace("-", " ").title()
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=page_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=author,
                section="piie_publication",
                tier=2,
                document_type=f"piie_{doc_type}",
            )
            yielded += 1
            time.sleep(0.5)

        log.info(
            "PIIE: yielded %d / %d candidates "
            "(body_failed=%d, no_date=%d, out_of_window=%d)",
            yielded, len(candidates), body_failed, no_date, out_of_window,
        )

    def _fetch_sitemap_page(self, sm_url: str, attempts: int = 7):
        """Fetch one ?page=N sitemap, fail-loud on transient errors.

        Returns the response on HTTP 200, or ``None`` on HTTP 404 (the
        end-of-pages signal). Retries 429/5xx/network with jittered backoff
        and raises ``RuntimeError`` on exhaustion or a hard block (e.g. 403),
        so a transient Cloudflare/Wayback-style hiccup can never be mistaken
        for the end of the sitemap and silently truncate discovery.
        """
        last: str | None = None
        for attempt in range(attempts):
            try:
                resp = self._piie_get(sm_url, timeout=60.0)
            except Exception as exc:  # network-level
                last = repr(exc)
            else:
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 404:
                    return None
                if resp.status_code in (429, 500, 502, 503, 504):
                    last = f"HTTP {resp.status_code}"
                else:
                    raise RuntimeError(
                        f"PIIE sitemap {sm_url}: HTTP {resp.status_code} "
                        "(hard block — Cloudflare may have tightened)"
                    )
            time.sleep(min(5.0 * (2 ** attempt), 320.0) + random.uniform(0, 1))
        raise RuntimeError(
            f"PIIE sitemap {sm_url}: exhausted {attempts} attempts ({last})"
        )

    def _discover_sitemap_urls(
        self, start: date, end: date,
    ) -> list[tuple[str, str]]:
        """Walk piie.com's paginated sitemap and return matching URLs.

        Returns ``[(url, doc_type), ...]`` for URLs whose path matches one
        of ``_URL_PATTERNS``. For publication URLs that encode a year in
        the path, we pre-filter on year so out-of-window publications are
        never fetched. Blog URLs (no year in path) are returned unfiltered
        and date-checked after body fetch.

        Discovery walks ``?page=1, 2, ...`` until the first 404 (see the
        class docstring). A transient error mid-walk raises rather than
        ending the walk early — under-capture must fail loud.
        """
        compiled = [(re.compile(p), d, y) for p, d, y in self._URL_PATTERNS]
        candidates: list[tuple[str, str]] = []
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        page = 1
        while page <= self._SITEMAP_MAX_PAGES:
            sm_url = f"{self._SITEMAP_URL}?page={page}"
            resp = self._fetch_sitemap_page(sm_url)
            if resp is None:
                break  # 404 → past the last page

            try:
                tree = ET.fromstring(resp.content)
            except ET.ParseError as exc:
                raise RuntimeError(
                    f"PIIE sitemap {sm_url}: XML parse failed ({exc})"
                ) from exc

            url_els = tree.findall("s:url", ns)
            if not url_els:
                break  # empty urlset → defensive end-of-pages

            for url_el in url_els:
                loc_el = url_el.find("s:loc", ns)
                if loc_el is None or not loc_el.text:
                    continue
                url = loc_el.text.strip()
                for pat, doc_type, year_grp in compiled:
                    m = pat.search(url)
                    if not m:
                        continue
                    if year_grp is not None:
                        try:
                            url_year = int(m.group(year_grp))
                        except (ValueError, IndexError):
                            url_year = None
                        if url_year is not None and (
                            url_year < start.year or url_year > end.year
                        ):
                            break
                    candidates.append((url, doc_type))
                    break

            page += 1
            time.sleep(0.3)

        return candidates

    def _cdx_enumerate(self) -> list[tuple[str, str]]:
        """Enumerate PIIE's full publication+blog URL set from Wayback CDX.

        Returns ``[(canonical_url, doc_type), ...]`` across all years for each
        prefix in ``_CDX_PREFIXES``. Fail-loud: a CDX outage raises rather than
        returning a short list that would be silently mistaken for a complete
        corpus (under-capture is the only failure mode we chase here).
        """
        out: list[tuple[str, str]] = []
        for prefix, doc_type in self._CDX_PREFIXES:
            urls = self._cdx_query(prefix)
            for u in urls:
                out.append((u, doc_type))
            log.info("PIIE CDX %s: %d distinct URLs", prefix, len(urls))
        return out

    def _cdx_query(self, prefix: str) -> list[str]:
        """One CDX prefix query → cleaned, deduped canonical article URLs.

        Uses ``matchType=prefix`` rather than the ``url=…*`` bulk-wildcard
        form. Both prefix-match the same URL set, but ADR-023 found the bulk
        wildcard non-deterministic under load (0/849/6575 rows across three
        runs of one query) and 503-prone — exactly the burst that killed job
        50493138. The ``matchType=prefix`` endpoint returns deterministically
        and is what CBO's ``_cdx_block`` already relies on. The trailing
        ``/`` base filter below still discards any sibling that shares the
        prefix string (e.g. realtime-economics vs realtime-economic-…).
        """
        # Built literally so requests doesn't percent-encode the filter colon.
        cdx_url = (
            f"{self._CDX_BASE}?url=piie.com/{prefix}&matchType=prefix"
            "&collapse=urlkey&filter=statuscode:200&fl=original&output=text"
        )
        text = self._cdx_get(cdx_url)
        base = f"piie.com/{prefix}/"
        seen: set[str] = set()
        urls: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            stripped = line.split("#", 1)[0].split("?", 1)[0]
            host_rel = re.sub(r"^https?://(www\.)?", "", stripped)
            if not host_rel.startswith(base):
                continue
            if self._CDX_ASSET_RE.search(host_rel):
                continue
            slug = host_rel[len(base):].strip("/")
            if not slug:
                continue  # bare section index
            last = slug.rsplit("/", 1)[-1]
            if self._CDX_YEAR_INDEX_RE.match(last):
                continue  # /type/2016 year-listing page, not an article
            canon = f"https://www.{host_rel.rstrip('/')}"
            key = canon.lower()
            if key in seen:
                continue
            seen.add(key)
            urls.append(canon)
        return urls

    def _cdx_get(self, cdx_url: str, attempts: int = 10) -> str:
        """GET a CDX endpoint with fail-loud jittered backoff.

        archive.org's CDX server 503s / times out *in multi-minute bursts*
        under load (observed repeatedly 2026-06-05). Retries transient
        failures and raises only on sustained outage or a hard status, so a
        Wayback hiccup can never silently truncate enumeration. Uses a
        (connect, read) tuple timeout per the project HTTP-timeout rule.

        10 attempts with the 5·2^n backoff (capped 240s) spans ~20 min of
        patience per query — enough to ride out a typical 503 burst. PIIE
        fires one query per prefix (8 of them); the prior 6-attempt / ~5-min
        ceiling let a single unlucky prefix kill a 2-hour job (job 50493138).
        """
        last: str | None = None
        for attempt in range(attempts):
            try:
                resp = requests.get(cdx_url, timeout=(10, 120))
            except Exception as exc:  # network-level
                last = repr(exc)
            else:
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code in (429, 500, 502, 503, 504):
                    last = f"HTTP {resp.status_code}"
                else:
                    raise RuntimeError(
                        f"PIIE CDX {cdx_url}: HTTP {resp.status_code} (hard)"
                    )
            if attempt < attempts - 1:  # no wasted sleep after the last try
                time.sleep(min(5.0 * (2 ** attempt), 240.0) + random.uniform(0, 1))
        raise RuntimeError(
            f"PIIE CDX {cdx_url}: exhausted {attempts} attempts ({last})"
        )


# ---------------------------------------------------------------------------
# Tier 1 — Congressional testimony
# ---------------------------------------------------------------------------


class CongressionalIngestor(Ingestor):
    """Fed Chair and Treasury Secretary testimony before Congress.

    Scope: Senate Banking Committee and House Financial Services Committee only.
    Approximately 6–10 hearings per year. Fed Chair testimony is available via
    the Federal Reserve's own website (supplementing fed.py which covers FOMC).
    Treasury Secretary testimony is retrieved through two complementary paths.

    Note: fed.py's FederalReserveIngestor already ingests Fed Chair testimony
    from federalreserve.gov/testimony. This ingestor fetches Treasury Secretary
    testimony from Treasury.gov, which is not covered elsewhere.

    To avoid duplicating Fed Chair testimony, this ingestor only fetches
    Treasury Secretary testimony.

    Dual retrieval path (introduced 2026-05-20 to close 2010-2023 coverage gap):

      Path A — Treasury Drupal press-release listing
        (``home.treasury.gov/news/press-releases?category=Secretary Statements & Remarks``)

        Date-DESC pagination. Reaches back to the late 1990s when walked to
        sufficient depth — page 1500 surfaces 1998 content, page 500 surfaces
        2015, page 200 surfaces 2023-Q1. Each page carries ~16 release links
        (3-6 of which are a "Latest releases" widget repeated on every page;
        the remainder are page-specific older entries). Path A produces both
        recent Bessent-era statements (modern ``/statements/<slug>``,
        ``/testimonies/<slug>``, ``/readouts/<slug>`` URLs) and legacy
        ``jl####`` (Lew), ``sm####`` (Yellen), ``mnu####`` (Mnuchin),
        ``tg####`` (Geithner) slug-based pages that Treasury preserved in
        the Drupal listing. ``_MAX_LISTING_PAGES`` was raised from 1200 to
        2500 on 2026-05-20 to ensure a 2010-window descent finishes within
        the page cap; sleep is 0.5s/page so a full descent is ~20 min wall.

      Path B — GovInfo CHRG (Congressional Hearings) collection
        (``api.govinfo.gov/collections/CHRG``)

        Independent defense-in-depth historical archive. CHRG is the GPO's
        canonical record of formal Congressional hearing transcripts, which
        includes every Treasury Secretary testimony before House Financial
        Services and Senate Banking dating to the 1990s. Long-form transcript
        register (verbatim Q&A) is a different register from Treasury's
        own press-release-style remarks, and is exactly the
        cross-cutting-Q&A dimension this ingestor exists to capture
        (ADR-020 basis-set rationale). Path B is rate-limited to one
        request/sec and walks the CHRG collection by year-window using the
        same ``GOVINFO_API_KEY`` pattern as ``CEAIngestor``. We filter for
        hearings whose ``title`` mentions the Treasury Secretary; for each
        match we fetch the GovInfo plain-text rendering and emit one
        ``Article`` per hearing. Coverage: ~6-12 hearings/year, 2010-present.

    Path A produces the recent + Drupal-archived material; Path B fills in
    historical coverage independently and is robust against Treasury layout
    changes. Both paths feed through the same ``seen`` set so duplicates
    (uncommon — different URL conventions) are de-duplicated by URL.
    """

    source_id = "congressional"

    # Secretary Statements & Remarks listing (Drupal, date-range filterable).
    # Treasury.gov links follow /news/press-releases/sb#### pattern.
    _LISTING_URL = "https://home.treasury.gov/news/press-releases"
    _TREASURY_BASE = "https://home.treasury.gov"

    # GovInfo CHRG (Congressional Hearings) historical archive — Path B.
    _GOVINFO_BASE = "https://api.govinfo.gov"
    _CHRG_COLLECTION = "CHRG"
    _DEMO_KEY = "DEMO_KEY"
    # Title-substring filter applied to CHRG package titles to identify
    # hearings featuring Treasury Secretary testimony. Hearings of interest
    # almost always carry "Secretary of the Treasury" or "Treasury Secretary"
    # in the title or in a granule sub-title; matching against the package
    # title alone is conservative (we may miss hearings titled by topic
    # without explicit mention of the Secretary) but avoids false positives
    # from hearings featuring Under/Assistant Secretaries. Case-insensitive.
    _CHRG_TITLE_RE = re.compile(
        r"\b(?:secretary\s+of\s+the\s+treasury|treasury\s+secretary)\b",
        re.IGNORECASE,
    )

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        # Path A — Treasury Drupal listing (recent + Drupal-archived legacy).
        yield from self._fetch_treasury_testimony(start, end, seen)
        # Path B — GovInfo CHRG historical hearings (2010-present coverage).
        yield from self._fetch_govinfo_chrg(start, end, seen)

    # Maximum number of listing pages to scan when paginating backward to a
    # historical window. Treasury press releases run ~5–10 per day under the
    # Secretary category; 2010-2026 covers roughly 16,000 entries at ~10
    # page-specific entries per Drupal page, so a 2010-anchored full descent
    # is ~1100-1200 pages. Bumped from 1200 to 2500 on 2026-05-20 — page 1500
    # surfaces 1998-vintage releases so 2500 gives a comfortable floor below
    # 2010 plus headroom for the runaway-loop bound. At 0.5s/page politeness
    # sleep a full 2500-page descent is ~21 min wall, acceptable for a
    # one-time historical ingest. Drupal returns 200 (with the
    # "Latest releases" widget but no new content) past the true end of the
    # archive, so we still rely on the no-next-link signal and the
    # ``oldest < start`` early-exit for actual termination.
    _MAX_LISTING_PAGES = 2500
    _LISTING_ROW_DATE_RE = re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2},\s+\d{4}\b"
    )

    # Match both the legacy short-slug pattern (sb0498, jy0001) and the modern
    # slug-path patterns Treasury introduced for statements / testimonies /
    # readouts in 2024+.
    _PRESS_RELEASE_HREF_RE = re.compile(
        r"^/news/press-releases/("
        r"[a-zA-Z]{2}\d+"                              # sb0498, jy0001 (legacy)
        r"|statements/[a-zA-Z0-9-]+"                   # /statements/<slug>
        r"|testimonies/[a-zA-Z0-9-]+"                  # /testimonies/<slug>
        r"|readouts/[a-zA-Z0-9-]+"                     # /readouts/<slug>
        r"|remarks/[a-zA-Z0-9-]+"                      # /remarks/<slug>
        r")"
    )

    def _fetch_treasury_testimony(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Scrape Treasury Secretary Statements & Remarks for testimony items.

        Treasury's Drupal listing IGNORES `date_filter[min]/[max]` query params
        on the server side as of 2026-05 — supplying them returns the standard
        newest-first ordering. To reach a historical window we therefore must
        paginate backward until the rows on a page are older than `start`.

        Per-row dates come from the `<time datetime=...>` element rendered next
        to each release title — preferred when present, with a text-regex
        fallback for older listing layouts. We filter on these before fetching
        individual article pages — avoiding one HTTP request per out-of-window
        release.

        Pre-fix bug (2026-05-13 dry run, 0 articles for 2024 window): the
        regex only matched `[a-zA-Z]{2}\\d+` slugs (e.g. sb0498), missing
        modern `/statements/<slug>`, `/testimonies/<slug>`, `/readouts/<slug>`
        URL forms. The relevance filter additionally hardcoded the Bessent-era
        "Economic Fury" branding as an exclusion, which dropped legitimate
        macro-financial Secretary remarks. Both fixed below.
        """
        consecutive_no_match_pages = 0
        total_yielded = 0
        page_one_links = 0
        for page in range(self._MAX_LISTING_PAGES):
            params: dict = {"category": "Secretary Statements & Remarks"}
            # The date filter params don't filter server-side, but submitting
            # them is harmless and preserves the intent in the URL.
            params["date_filter[min]"] = start.isoformat()
            params["date_filter[max]"] = end.isoformat()
            if page > 0:
                params["page"] = page
            try:
                resp = requests.get(
                    self._LISTING_URL,
                    params=params,
                    headers=_HEADERS,
                    timeout=(10.0, 30.0),
                )
                if resp.status_code == 404:
                    if page == 0:
                        raise RuntimeError(
                            f"Treasury listing page 0 → HTTP 404 ({self._LISTING_URL}) "
                            f"— listing URL is gone; refusing to yield an empty series"
                        )
                    log.info("Treasury listing page %d → 404; end of pagination", page)
                    break
                resp.raise_for_status()
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(
                    f"Treasury listing page {page} failed: {exc} — refusing to "
                    f"silently truncate the Secretary-remarks series"
                ) from exc

            soup = BeautifulSoup(resp.text, "lxml")
            release_links = [
                a for a in soup.find_all("a", href=True)
                if self._PRESS_RELEASE_HREF_RE.match(a["href"])
                and len(a.get_text(strip=True)) > 15
            ]

            if page == 0:
                page_one_links = len(release_links)
                if page_one_links == 0:
                    # Layout shift: regex no longer matches anything. Fail
                    # loudly rather than silently returning 0 articles.
                    log.error(
                        "Treasury listing page 0: 0 release links matched "
                        "_PRESS_RELEASE_HREF_RE. Treasury layout may have "
                        "changed — broken silently on prior dry runs."
                    )
                    return
                log.info("Treasury listing: page 0 = %d release links", page_one_links)

            if not release_links:
                log.info("Treasury listing page %d: no release links — stopping", page)
                break

            # Resolve each link's date — prefer <time datetime=...>, fall back
            # to the surrounding-text regex for older listings.
            rows = [self._extract_row_date(link) for link in release_links]
            valid_dates = [d for d in rows if d is not None]
            oldest = min(valid_dates) if valid_dates else None
            newest = max(valid_dates) if valid_dates else None

            if page == 0 and not valid_dates:
                log.error(
                    "Treasury listing page 0: 0 dates extracted from %d "
                    "release rows. Date selector broken — aborting.",
                    page_one_links,
                )
                return

            page_matches = 0
            for link, row_date in zip(release_links, rows):
                if row_date is None:
                    continue
                if row_date < start or row_date > end:
                    continue
                href = link["href"]
                url = self._TREASURY_BASE + href
                if url in seen:
                    continue
                title = link.get_text(strip=True)
                if not self._is_relevant(title):
                    continue

                seen.add(url)
                body, fetched_title, author, page_date = _fetch_page_full(url, min_words=100)
                # Floor at 100 words filters out media advisories (~50-80
                # word announcements like "Secretary will testify on X day
                # before Y committee") while still capturing real
                # statements (typically 800-3000 words) and meaningful
                # readouts (200-500 words). Below 100 the record contributes
                # no narrative content for the embedding stage.
                if not body or len(body.split()) < 100:
                    continue
                # Prefer the article-page date (more precise) but fall back to
                # the listing-row date when the page omits it.
                published = page_date or row_date
                if published < start or published > end:
                    continue
                page_matches += 1
                total_yielded += 1

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=published.isoformat() + "T00:00:00Z",
                    title=fetched_title or title or "Treasury Secretary Testimony",
                    body=body,
                    author=author,
                    section="treasury_testimony",
                    tier=1,
                    document_type="congressional_testimony",
                    extra_meta={"retrieval_path": "treasury_drupal"},
                )
                time.sleep(1.0)

            log.info(
                "Treasury listing page %d: links=%d in-window=%d yielded=%d "
                "(rows: oldest=%s newest=%s)",
                page, len(release_links),
                sum(1 for d in rows if d is not None and start <= d <= end),
                page_matches, oldest, newest,
            )

            # Stop once we've paginated past the requested window.
            if oldest is not None and oldest < start:
                log.info("Treasury listing: reached page %d with oldest date %s < start %s — stopping",
                         page, oldest, start)
                break

            # Safety: if we drift far past the window without finding anything
            # for many pages in a row, bail out instead of grinding to MAX_PAGES.
            if page_matches == 0:
                consecutive_no_match_pages += 1
                # When we're still future-of-window (newest > end), keep paging
                # back. When we're past-of-window (oldest < start) we would
                # have already broken above. The remaining case is "fully
                # inside window but nothing matched relevance filter" — give
                # it 50 pages of slack before giving up.
                if (newest is not None and newest <= end
                        and consecutive_no_match_pages >= 50):
                    log.info("Treasury listing: 50 consecutive in-window pages with no "
                             "relevant matches at page %d — stopping early", page)
                    break
            else:
                consecutive_no_match_pages = 0

            # Defer to Drupal's own "next page" link as the canonical stop
            # signal. Treasury renders title="Go to next page" (not "Next
            # page" — that was the historical Drupal default), so we check
            # both plus rel="next" as a final fallback.
            next_link = soup.select_one(
                "a[rel='next'], a[title='Go to next page'], "
                ".pager__item--next a, a[title='Next page']"
            )
            if not next_link:
                log.info("Treasury listing page %d: no next page link — stopping", page)
                break
            time.sleep(0.5)
        else:
            log.warning("Treasury listing: hit MAX_LISTING_PAGES=%d before crossing start=%s",
                        self._MAX_LISTING_PAGES, start)

        log.info("Treasury listing: total yielded = %d", total_yielded)

    def _extract_row_date(self, link) -> date | None:
        """Find the publication date for a release link in the listing HTML.

        Modern listings (2024+) render a `<time datetime="2026-05-11T...">`
        element next to each release. We prefer that when present (most
        reliable), falling back to a text-regex over up to 4 ancestor nodes
        for older layouts.
        """
        # Walk up to 4 ancestors looking for a sibling/child <time> element.
        node = link
        for _ in range(4):
            node = node.parent if node else None
            if node is None:
                break
            time_el = node.find("time", attrs={"datetime": True})
            if time_el:
                dt_str = time_el.get("datetime", "")
                # ISO-8601: YYYY-MM-DDTHH:MM:SSZ — date.fromisoformat handles
                # the date prefix even if a 'T...' suffix follows in newer pys,
                # but we slice to be defensive across Python versions.
                try:
                    return date.fromisoformat(dt_str[:10])
                except ValueError:
                    pass
            text = node.get_text(" ", strip=True)
            m = self._LISTING_ROW_DATE_RE.search(text)
            if m:
                parsed = _parse_date_flexible(m.group(0))
                if parsed:
                    return parsed
        return None

    # ------------------------------------------------------------------
    # Path B — GovInfo CHRG (Congressional Hearings) historical archive
    # ------------------------------------------------------------------

    @classmethod
    def _govinfo_api_key(cls) -> str:
        key = os.environ.get("GOVINFO_API_KEY")
        if not key:
            raise RuntimeError(
                "GOVINFO_API_KEY environment variable is not set. The CHRG "
                "path (Congressional Path B, ADR-021) requires an authenticated "
                "GovInfo API key to enumerate Treasury Secretary hearings at "
                "full coverage; the public DEMO_KEY is rate-limited to 30 "
                "requests/hour and would silently undercover the historical "
                "window. Sign up free at https://api.govinfo.gov/signup/ and "
                "set GOVINFO_API_KEY in .env before re-running the ingest."
            )
        return key

    def _fetch_govinfo_chrg(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Walk the GovInfo CHRG collection for Treasury Secretary hearings.

        Strategy: walk packages in the CHRG collection issued within
        ``[start, end]`` using the published-since endpoint (same pattern as
        :class:`CEAIngestor` but against ``CHRG`` instead of ``ERP``). For
        each package whose title mentions the Treasury Secretary, fetch the
        plain-text hearing transcript granule and emit one ``Article``.

        Why CHRG and not Treasury Drupal as the historical primary:
          - CHRG is the canonical GPO-deposited Congressional record, not
            subject to Treasury layout changes, with stable package IDs.
          - The hearing-transcript register (verbatim Q&A) is precisely the
            cross-cutting Q&A dimension this ingestor exists to capture
            (ADR-020 basis-set rationale) — different in register from
            Treasury's own press-release-style summaries that Path A
            captures.
          - Coverage is independent of Treasury's pagination cap, so even
            if Drupal layout breaks, historical Secretary testimony remains
            accessible.

        Politeness: 1.0s between package walks, 0.5s between granule fetches.
        Typical yield is 6-12 hearings/year, so the full 2010-2026 walk is
        ~100-200 hearings — modest.
        """
        api_key = self._govinfo_api_key()
        total_yielded = 0
        total_title_match = 0
        for package in self._chrg_list_packages(api_key, start, end):
            package_id = package.get("packageId")
            title = (package.get("title") or "").strip()
            if not package_id or not title:
                continue
            if not self._CHRG_TITLE_RE.search(title):
                continue
            total_title_match += 1
            # IMPORTANT: package.dateIssued is the GPO publication date —
            # the date the transcript was deposited, which can be months
            # AFTER the hearing actually happened. For the dynamics analysis
            # the discourse event is dated to when it was given (testimony
            # date), not when GPO published the record. Fetch the package
            # summary to read heldDates[0] (the authoritative hearing date).
            held_date = self._chrg_held_date(api_key, package_id)
            if not held_date:
                log.debug(
                    "Congressional CHRG %s: no heldDate available; dropping",
                    package_id,
                )
                continue
            if held_date < start or held_date > end:
                continue
            article = self._chrg_build_article(
                api_key=api_key,
                package_id=package_id,
                title=title,
                held_date=held_date,
                seen=seen,
            )
            if article is not None:
                total_yielded += 1
                yield article
            time.sleep(0.5)
        log.info(
            "Congressional CHRG: title matches=%d, yielded=%d",
            total_title_match, total_yielded,
        )

    def _chrg_held_date(
        self, api_key: str, package_id: str,
    ) -> date | None:
        """Fetch the actual hearing date for a CHRG package.

        Each CHRG package's ``/summary`` endpoint exposes a ``heldDates``
        list — the date(s) the hearing was held. Returns the first held
        date. Falls back to ``dateIssued`` only if the summary endpoint
        fails to return heldDates (very rare; pre-2005 hearings sometimes
        lack it).
        """
        url = (
            f"{self._GOVINFO_BASE}/packages/{package_id}/summary"
            f"?api_key={api_key}"
        )
        try:
            resp = _get(url, timeout=30.0)
            data = resp.json()
        except Exception as exc:
            log.debug(
                "Congressional CHRG %s summary fetch failed: %s",
                package_id, exc,
            )
            return None
        held = data.get("heldDates") or []
        if held:
            parsed = self._parse_iso_date(held[0])
            if parsed:
                return parsed
        # Fallback to dateIssued — should be rare.
        return self._parse_iso_date(data.get("dateIssued"))

    def _chrg_list_packages(
        self, api_key: str, start: date, end: date,
    ) -> Iterator[dict]:
        """Yield CHRG package summaries whose lastModified is in a window.

        IMPORTANT: GovInfo's ``/collections/{name}/{since}/{until}`` endpoint
        filters on the package's ``lastModified`` timestamp, NOT on the
        hearing date or publication date. The semantics is "packages that
        appeared or were re-indexed within [since, until]." We therefore
        need to walk a LARGER lastModified window than the requested
        hearing-date window:

        - A hearing held on 2010-03-15 might have its transcript published
          to GovInfo on 2010-09-XX (typical 3-9 month publish lag).
        - Subsequent re-indexings (corrections, OCR updates) can push the
          lastModified date forward by years.

        So a hearing in our window can have lastModified anywhere from
        the hearing date forward. We walk lastModified from
        ``start - 0 days`` (the hearing date is also the earliest possible
        publish/index date) through *now* with no upper bound, then filter
        by the package summary's authoritative ``heldDates`` field in the
        caller (``_fetch_govinfo_chrg``).

        The cost: walking the full lastModified-since window touches more
        packages than we need (we pull and discard non-Treasury hearings),
        but CHRG title filtering is cheap (regex on summary objects).
        """
        # Walk lastModified from the hearing-window start onward. No upper
        # bound — the caller's heldDate filter is what bounds the result.
        anchor = start
        anchor_iso = anchor.isoformat() + "T00:00:00Z"
        url = (
            f"{self._GOVINFO_BASE}/collections/{self._CHRG_COLLECTION}/"
            f"{anchor_iso}"
            f"?offsetMark=*&pageSize=100&api_key={api_key}"
        )
        page = 0
        while True:
            page += 1
            try:
                resp = _get(url, timeout=60.0)
                data = resp.json()
            except Exception as exc:
                raise RuntimeError(
                    f"Congressional CHRG package list failed on page {page} after "
                    f"retries — refusing to silently truncate the hearing series"
                ) from exc
            packages = data.get("packages", [])
            if not packages:
                return
            for pkg in packages:
                yield pkg
            # GovInfo paginates via ``nextPage`` — a fully-formed URL carrying
            # the opaque offsetMark cursor already URL-encoded. Follow it
            # directly; it omits our api_key, so append it. (Splicing nextPage
            # in as if it were the bare offsetMark token produced a nested URL
            # GovInfo 500s on — ADR-030.)
            next_page = data.get("nextPage")
            if not next_page or next_page == url:
                return
            if "api_key=" not in next_page:
                next_page += f"&api_key={api_key}"
            url = next_page
            time.sleep(1.0)
            # Safety bound. CHRG has ~3000 hearings/year × 16 years = 48k
            # packages at pageSize=100 = ~480 pages. Bail at 1000 to avoid
            # an infinite loop if the API contract drifts.
            if page > 1000:
                raise RuntimeError(
                    "Congressional CHRG package list exceeded 1000 pages — API "
                    "contract likely drifted; refusing to truncate silently"
                )

    def _chrg_build_article(
        self,
        *,
        api_key: str,
        package_id: str,
        title: str,
        held_date: date,
        seen: set[str],
    ) -> Article | None:
        """Download the hearing's full transcript text and build an Article.

        ``held_date`` is the authoritative hearing date from the package's
        ``heldDates[0]`` field — used as published_at on the Article so the
        dynamics analysis aligns records with when the testimony was given,
        not when GPO published the transcript.

        CHRG body strategy (verified 2026-05-20 on CHRG-115hhrg33428):
          1. Public PDF (``govinfo.gov/content/pkg/{pkg}/pdf/{pkg}.pdf``)
             — typically 5-50 MB per hearing, contains the complete verbatim
             transcript. No API key required. We extract text with pypdf,
             matching :class:`CEAIngestor`'s ERP extraction.
          2. Fallback: API ``/packages/{pkg}/htm`` (uses api_key quota).
             CHRG's htm rendering is often just the cover page (no full
             transcript), so this is a salvage path only — most hearings
             will succeed at step 1.

        Why PDF and not html: GovInfo CHRG HTML renderings frequently
        contain only the title page with "[NO TEXT AVAILABLE]" body
        (the full text is delivered as PDF only). PDF parsing is slower
        but produces the actual transcript text needed for embedding.
        """
        public_url = f"https://www.govinfo.gov/app/details/{package_id}"
        if public_url in seen:
            return None
        # Step 1: public PDF (no API key needed).
        pdf_url = (
            f"https://www.govinfo.gov/content/pkg/{package_id}/pdf/{package_id}.pdf"
        )
        body = self._extract_pdf_text(pdf_url)
        # Step 2: API htm fallback if PDF extraction failed.
        if not body or len(body.split()) < 100:
            htm_url = (
                f"{self._GOVINFO_BASE}/packages/{package_id}/htm"
                f"?api_key={api_key}"
            )
            try:
                resp = _get(htm_url, timeout=60.0)
                if resp.status_code == 200 and resp.text:
                    extracted = trafilatura.extract(
                        resp.text, include_comments=False, include_tables=False
                    )
                    if extracted and len(extracted.split()) >= 100:
                        body = extracted
            except Exception as exc:
                log.debug(
                    "Congressional CHRG api/htm %s failed: %s",
                    package_id, exc,
                )
        if not body or len(body.split()) < 100:
            log.debug("Congressional CHRG %s: body < 100 words — skipping", package_id)
            return None
        seen.add(public_url)
        return _make_article(
            source_id=self.source_id,
            url=public_url,
            published_at=held_date.isoformat() + "T00:00:00Z",
            title=title,
            body=body,
            author="U.S. Congress",
            section="treasury_testimony",
            tier=1,
            document_type="congressional_testimony",
            extra_meta={
                "package_id": package_id,
                "govinfo_collection": self._CHRG_COLLECTION,
                "retrieval_path": "govinfo_chrg",
            },
        )

    @staticmethod
    def _parse_iso_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    @staticmethod
    def _extract_pdf_text(pdf_url: str) -> str:
        """Download a CHRG PDF and return its extracted text.

        Raises ImportError if pypdf is unavailable — Path B's PDF
        extraction is mandatory for full coverage of modern hearings.
        Mirrors :meth:`CEAIngestor._extract_pdf_text`. CHRG PDFs are
        text-layered (not scanned) for post-2000 hearings; older
        pre-2000 hearings may have been OCR'd. A transient fetch/parse
        error returns "" so the caller falls through to the API htm
        endpoint.
        """
        from pypdf import PdfReader
        from io import BytesIO
        try:
            resp = _get(pdf_url, timeout=60.0)
        except Exception as exc:
            log.debug("Congressional CHRG PDF fetch %s failed: %s", pdf_url, exc)
            return ""
        try:
            reader = PdfReader(BytesIO(resp.content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(p.strip() for p in pages if p.strip())
        except Exception as exc:
            log.debug("Congressional CHRG PDF parse %s failed: %s", pdf_url, exc)
            return ""

    # Congressional appearance markers — these aren't topic keywords, they
    def _is_relevant(self, title: str) -> bool:
        """Structural role guard only (ADR-016).

        Tier-1 Congressional ingest is by definition Secretary-level — drop
        releases by under/assistant secretaries and deputies. Everything else
        (topic relevance, sanctions-vs-macro-framing disambiguation) is
        delegated to Stage 2's canonical filter where the BODY of each
        release is available, not just the title.

        Pre-2026-05-13 the filter additionally hardcoded a "sanctions"
        exclusion that misfired on Treasury's "Economic Fury" branding (which
        IS macro-financial discourse — Iran oil sanctions framing, banking
        penalties). Removing the title-only sanctions gate avoids that whole
        class of mis-rejection; the canonical Stage 2 filter sees the full
        body and applies the same keyword + embedding gates as everywhere else.
        """
        tl = title.lower()
        if re.search(r"\bunder ?secretary\b|\bassistant secretary\b|\bdeputy\b", tl):
            return False
        return True


# ---------------------------------------------------------------------------
# Tier 1 — US fiscal authority (executive branch)
# ---------------------------------------------------------------------------


class CEAIngestor(Ingestor):
    """Council of Economic Advisers — Economic Report of the President.

    Sources the executive-branch macro voice (basis-set dimension 5 in
    ADR-020). Retrieval via the govinfo.gov JSON API against the ERP
    collection, which contains every Economic Report of the President
    back to 1947 with chapter-level granules (61 packages / ~3,040
    granules in total).

    Why govinfo and not whitehouse.gov:
      - govinfo.gov is the canonical GPO-deposited record, not bot-protected,
        and has a documented JSON API with stable package/granule URIs.
      - whitehouse.gov/cea/ pages are bot-protected (Cloudflare/JS) and
        their URL structure changes between administrations. The govinfo
        ERP collection captures the same authoritative annual document
        without that operational risk.

    Coverage:
      - One ``Article`` per chapter-level granule. The whole ERP
        is ~400 pages/year split into ~15-25 chapters; chapter granularity
        is what gives meaningful narrative-level documents for clustering
        (the full-report monolith would dominate one cluster).
      - PDF text via pypdf. The ERP PDFs are text-layered (not scanned),
        so extraction is clean.

    API key:
      - ``GOVINFO_API_KEY`` env var is required. The ingestor raises
        ``RuntimeError`` if it is not set rather than silently falling
        back to the public DEMO_KEY (30 req/hr), which would stall the
        full-corpus enumeration. Free signup at https://api.govinfo.gov/signup/.
    """

    source_id = "cea"

    _GOVINFO_BASE = "https://api.govinfo.gov"
    _COLLECTION = "ERP"
    _PUBLISH_DATE_FMT = "%Y-%m-%d"

    @classmethod
    def _api_key(cls) -> str:
        key = os.environ.get("GOVINFO_API_KEY")
        if not key:
            raise RuntimeError(
                "GOVINFO_API_KEY environment variable is not set. CEAIngestor "
                "requires an authenticated GovInfo API key to enumerate the "
                "ERP collection; the public DEMO_KEY is rate-limited to 30 "
                "requests/hour and would not finish the full ingest. Sign up "
                "free at https://api.govinfo.gov/signup/ and set "
                "GOVINFO_API_KEY in .env before re-running."
            )
        return key

    @classmethod
    def _govinfo_get_json(cls, url: str, *, max_attempts: int = 6) -> dict:
        """GET a govinfo JSON endpoint, retrying 429 / 5xx / network.

        The shared ``_get`` does NOT retry 429 (it classifies 4xx as
        non-retryable), but govinfo throttles bursts with 429 even on a
        real key. A swallowed 429 on a listing call would silently truncate
        the package/granule enumeration — a coverage hole. So we retry here
        and raise RuntimeError on exhaustion (fail-loud → checkpoint re-run).
        """
        safe = cls._redact_key(url)
        backoff = 3.0
        last_err: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=(10.0, 60.0))
            except Exception as exc:
                last_err = str(exc)
                log.debug("CEA govinfo %s: %s (attempt %d/%d) — backoff %.1fs",
                          safe, last_err, attempt, max_attempts, backoff)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff *= 2
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
                log.debug("CEA govinfo %s: %s (attempt %d/%d) — backoff %.1fs",
                          safe, last_err, attempt, max_attempts, backoff)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff *= 2
                continue
            raise RuntimeError(f"CEA govinfo {safe}: unexpected HTTP {resp.status_code}")
        raise RuntimeError(
            f"CEA govinfo fetch failed after {max_attempts} attempts "
            f"(last error: {last_err}) for {safe} — refusing to silently "
            "truncate the ERP enumeration"
        )

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        api_key = self._api_key()
        # Walk packages in the ERP collection within the date window.
        for package in self._list_packages(api_key, start, end):
            package_id = package.get("packageId")
            if not package_id:
                continue
            issued = self._parse_iso_date(package.get("dateIssued"))
            if not issued or issued < start or issued > end:
                continue
            yield from self._fetch_granules(api_key, package_id, issued)
            time.sleep(0.5)

    def _list_packages(
        self, api_key: str, start: date, end: date,
    ) -> Iterator[dict]:
        """Yield ERP package summaries with dateIssued in [start, end].

        Uses the published-since endpoint with year-prior buffer to catch
        ERPs whose lastModified is later than dateIssued.
        """
        # The collection-published endpoint requires an ISO start. Pad to
        # one year before the window opens so we don't miss a delayed
        # ingest of a prior-year ERP.
        anchor = max(date(2009, 1, 1), date(start.year - 1, 1, 1))
        anchor_iso = anchor.isoformat() + "T00:00:00Z"
        url = (
            f"{self._GOVINFO_BASE}/collections/{self._COLLECTION}/{anchor_iso}"
            f"?offsetMark=*&pageSize=100&api_key={api_key}"
        )
        page = 0
        while True:
            page += 1
            data = self._govinfo_get_json(url)
            packages = data.get("packages", [])
            if not packages:
                return
            for pkg in packages:
                yield pkg
            # See _chrg_list_packages: follow GovInfo's fully-formed nextPage
            # URL directly rather than splicing it in as an offsetMark token
            # (the latter produces a nested URL GovInfo 500s on — ADR-030).
            next_page = data.get("nextPage")
            if not next_page or next_page == url:
                return
            if "api_key=" not in next_page:
                next_page += f"&api_key={api_key}"
            url = next_page
            time.sleep(0.5)
            # Safety bound — ERP has ~61 packages historical; should fit in
            # one or two pages. Bail at 10 pages to avoid an infinite loop
            # if the API contract drifts.
            if page > 10:
                raise RuntimeError(
                    "CEA package list exceeded 10 pages — API contract likely "
                    "drifted; refusing to truncate silently"
                )

    def _fetch_granules(
        self, api_key: str, package_id: str, issued: date,
    ) -> Iterator[Article]:
        """Yield one Article per chapter-level granule of one ERP package."""
        url = (
            f"{self._GOVINFO_BASE}/packages/{package_id}/granules"
            f"?api_key={api_key}&pageSize=200&offsetMark=*"
        )
        data = self._govinfo_get_json(url)
        granules = data.get("granules", [])
        log.info("CEA: package %s issued=%s — %d granules",
                 package_id, issued.isoformat(), len(granules))
        for gran in granules:
            granule_id = gran.get("granuleId")
            if not granule_id:
                continue
            # Skip statistical-table granules: ERP includes ~20 chapter
            # granules + ~50 appendix tables per volume. Tables (granule
            # IDs containing "table") are short statistical summaries
            # (~400 words of column headers + numbers), not narrative
            # text; including them dilutes the per-cluster signal in
            # the discourse analysis.
            if "table" in granule_id.lower():
                continue
            article = self._build_article(
                api_key=api_key,
                package_id=package_id,
                granule_id=granule_id,
                granule=gran,
                issued=issued,
            )
            if article is not None:
                yield article
            time.sleep(0.3)

    def _build_article(
        self,
        *,
        api_key: str,
        package_id: str,
        granule_id: str,
        granule: dict,
        issued: date,
    ) -> Article | None:
        """Download granule PDF, extract text, return an Article (or None)."""
        title = (granule.get("title") or "").strip()
        # govinfo URL convention: granule HTML page on the public site.
        public_url = (
            f"https://www.govinfo.gov/app/details/{package_id}/{granule_id}"
        )
        pdf_url = (
            f"{self._GOVINFO_BASE}/packages/{package_id}/granules/{granule_id}"
            f"/pdf?api_key={api_key}"
        )
        body = self._extract_pdf_text(pdf_url)
        if not body or len(body.split()) < 100:
            log.debug("CEA: %s/%s skipped — PDF text < 100 words", package_id, granule_id)
            return None
        return _make_article(
            source_id=self.source_id,
            url=public_url,
            published_at=issued.isoformat() + "T00:00:00Z",
            title=title or f"ERP {issued.year} — {granule_id}",
            body=body,
            author="Council of Economic Advisers",
            section="cea_erp_chapter",
            tier=1,
            document_type="cea_erp_chapter",
            extra_meta={
                "package_id": package_id,
                "granule_id": granule_id,
                "govinfo_collection": self._COLLECTION,
            },
        )

    @staticmethod
    def _redact_key(url: str) -> str:
        """Strip the api_key query param so it never reaches logs."""
        return re.sub(r"api_key=[^&]+", "api_key=***", url)

    @classmethod
    def _extract_pdf_text(cls, pdf_url: str) -> str:
        """Download a granule PDF and return its extracted text.

        Two failure registers, deliberately distinguished so we never
        silently drop a chapter (the user's "no holes" requirement):
          - FETCH failure (429 / 5xx / network) — transient infrastructure.
            ``_fetch_pdf_bytes`` retries with backoff and raises RuntimeError
            on exhaustion, so a persistent throttle fails the CEA ingest
            loudly (checkpoint re-run + dedup) instead of emitting a partial
            chapter set. This matters because govinfo throttles bursts even
            with a real key, and the shared ``_get`` does NOT retry 429
            (it's a 4xx) — so the retry has to live here.
          - PARSE failure (pypdf can't read a successfully-downloaded PDF) —
            a permanent property of that one granule; retrying can't help.
            Logged at WARNING (not silent) and skipped via "".

        Raises ImportError if pypdf is unavailable — CEA cannot operate
        without it.
        """
        from pypdf import PdfReader
        from io import BytesIO
        content = cls._fetch_pdf_bytes(pdf_url)
        try:
            reader = PdfReader(BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(p.strip() for p in pages if p.strip())
        except Exception as exc:
            log.warning("CEA PDF parse failed (skipping this granule): %s — %s",
                        cls._redact_key(pdf_url), exc)
            return ""

    @classmethod
    def _fetch_pdf_bytes(cls, pdf_url: str, *, max_attempts: int = 6) -> bytes:
        """Download a govinfo PDF, retrying 429 / 5xx / network with backoff.

        Raises RuntimeError on exhaustion — a persistent fetch failure must
        fail the ingest loudly rather than silently drop an ERP chapter.
        """
        safe = cls._redact_key(pdf_url)
        backoff = 3.0
        last_err: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.get(pdf_url, headers=_HEADERS, timeout=(10.0, 60.0))
            except Exception as exc:
                last_err = str(exc)
                log.debug("CEA PDF %s: %s (attempt %d/%d) — backoff %.1fs",
                          safe, last_err, attempt, max_attempts, backoff)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff *= 2
                continue
            if resp.status_code == 200:
                return resp.content
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
                log.debug("CEA PDF %s: %s (attempt %d/%d) — backoff %.1fs",
                          safe, last_err, attempt, max_attempts, backoff)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
                backoff *= 2
                continue
            raise RuntimeError(f"CEA PDF {safe}: unexpected HTTP {resp.status_code}")
        raise RuntimeError(
            f"CEA PDF fetch failed after {max_attempts} attempts "
            f"(last error: {last_err}) for {safe} — refusing to silently "
            "drop an ERP chapter"
        )

    @staticmethod
    def _parse_iso_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Tier 2 — academic primary work (NBER restored, ADR-020)
# ---------------------------------------------------------------------------


class NBERIngestor(Ingestor):
    """NBER working papers via direct URL enumeration.

    Restored by ADR-020 (2026-05-20). The prior NBERIngestor (deleted in
    ADR-019) relied on the search API, which is bot-protected. This
    implementation enumerates ``/papers/wNNNNN`` directly — the spike
    on 2026-05-20 confirmed every probe returned HTTP 200, plain
    Drupal/nginx, no Cloudflare or DataDome, with citation_* meta tags
    (Google Scholar convention) providing structured metadata.

    Strategy:
      - Use a per-year paper-number floor (calibrated 2026-05-20) so the
        ingest doesn't pay the cost of enumerating every wNNNNN ID since
        1973.
      - Enumerate forward from the start-year floor through the end-year
        ceiling (capped at the head of NBER's series, discovered by
        probing forward until N consecutive misses).
      - Read citation_publication_date from each paper's meta tags;
        drop papers outside [start, end].
      - Body = title + abstract (NBER's working papers page exposes
        the abstract in the page body; trafilatura extracts it cleanly).

    Pre-clustering filter NOT applied (ADR-020). Every NBER paper in the
    window is ingested; post-clustering JEL classification decides which
    clusters are macro for dynamics analysis. This is symmetric with the
    other basis-set sources.

    Politeness: ~1 second between requests. Full 2010-2026 enumeration
    is ~30,000 IDs at 1 req/sec ≈ 8 hours wall clock; that's a one-time
    cost on RCC.
    """

    source_id = "nber"

    _PAPER_URL_TEMPLATE = "https://www.nber.org/papers/{paper_id}"

    # Calibrated by probing /papers/wNNNNN dates on 2026-05-20.
    # Each entry is the first paper ID whose citation_publication_date
    # is on or after January 1 of that year. Conservative starting
    # points (a few hundred IDs early so we don't miss late-published
    # papers from the prior year).
    _PAPER_FLOOR_BY_YEAR: dict[int, int] = {
        2010: 15500,   # w15500 = 2009-11-12 (Nov 2009)
        2011: 16700,
        2012: 17600,
        2013: 18700,
        2014: 19800,   # w20000 = 2014-03-20
        2015: 20800,
        2016: 21800,
        2017: 22900,   # w23000 = 2017-01-02
        2018: 24100,
        2019: 25400,
        2020: 26500,
        2021: 28100,   # w29000 = 2021-07-05
        2022: 29500,
        2023: 30800,
        2024: 31900,   # w32000 = 2024-01-01
        2025: 33000,
        2026: 33900,
    }

    # Stop enumeration after this many consecutive 404s — indicates we've
    # walked past the head of the series. This is the REAL terminator for
    # open-ended (to-present) runs: overshooting the true head is free
    # because the walk stops 30 IDs past it, so the ceiling below only
    # needs to be a generous backstop that never binds below the head.
    _STOP_AFTER_CONSECUTIVE_404S = 30

    # NBER publishes ~1500 working papers per year. Per-year headroom used
    # when projecting a ceiling past the latest calibrated year. Exceeds
    # the true publication rate so a stale table can never bind the ceiling
    # below the series head before the consecutive-404 stop fires.
    _ID_HEADROOM_PER_FORECAST_YEAR = 2500

    # Papers near a calendar boundary publish slightly out of ID order, so
    # an end_year paper can carry an ID just above the next year's floor.
    # Walk this far past a bounding floor so windowed runs don't clip them.
    _BOUNDARY_BUFFER = 400

    def _compute_ceiling(self, end_year: int) -> int:
        """Compute the upper paper-ID backstop for an enumeration.

        Two regimes:

        - Bounded window (``end_year`` is well inside the calibrated table):
          use the next-year floor plus a small boundary buffer so we stop
          enumerating once past the window without paying to walk to the
          live series head.
        - Open-ended / to-present (``end_year`` at or beyond the latest
          calibrated year): project forward generously. Because the
          consecutive-404 stop terminates the walk at the true head + 30,
          a too-high ceiling costs nothing, while a too-low one silently
          under-captures — so we deliberately overshoot.
        """
        if (next_year_floor := self._PAPER_FLOOR_BY_YEAR.get(end_year + 1)):
            return next_year_floor + self._BOUNDARY_BUFFER
        latest_year = max(self._PAPER_FLOOR_BY_YEAR)
        latest_floor = self._PAPER_FLOOR_BY_YEAR[latest_year]
        # +1 extra year of headroom guarantees the backstop stays above the
        # head even if the calibrated table is a year or two stale.
        years_forward = max(1, end_year - latest_year + 1) + 1
        return latest_floor + self._ID_HEADROOM_PER_FORECAST_YEAR * years_forward

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        floor_year = start.year
        ceiling_year = end.year
        floor = self._PAPER_FLOOR_BY_YEAR.get(
            floor_year, min(self._PAPER_FLOOR_BY_YEAR.values()),
        )
        ceiling = self._compute_ceiling(ceiling_year)
        log.info(
            "NBER: enumerating paper IDs w%d..w%d for window %s..%s",
            floor, ceiling, start.isoformat(), end.isoformat(),
        )

        consecutive_404 = 0
        yielded = 0
        examined = 0
        for n in range(floor, ceiling + 1):
            paper_id = f"w{n}"
            url = self._PAPER_URL_TEMPLATE.format(paper_id=paper_id)
            try:
                resp = _get(url, timeout=30.0)
            except requests.exceptions.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if status == 404:
                    consecutive_404 += 1
                    if consecutive_404 >= self._STOP_AFTER_CONSECUTIVE_404S:
                        log.info(
                            "NBER: stopping at %s — %d consecutive 404s "
                            "(walked off head of series)",
                            paper_id, consecutive_404,
                        )
                        break
                    continue
                # A non-404 HTTP error that survived _get's 5 retries is not a
                # gap in the ID sequence — it's systemic (NBER 5xx outage, or
                # 403/429 bot-blocking). Skipping it would silently drop this
                # paper and likely many more across the ~30k-ID walk, so fail loud.
                raise RuntimeError(
                    f"NBER {paper_id} ({url}): HTTP {status} after retries — "
                    f"failing loud rather than silently skipping"
                ) from exc
            except Exception as exc:
                # Connection/timeout that survived retries — systemic, not a gap.
                raise RuntimeError(
                    f"NBER {paper_id} ({url}): {exc} after retries — "
                    f"failing loud rather than silently skipping"
                ) from exc
            consecutive_404 = 0
            examined += 1

            article = self._parse_paper(paper_id, url, resp.text, start, end)
            if article is not None:
                yield article
                yielded += 1
            time.sleep(0.6)  # politeness

        log.info(
            "NBER: examined %d papers, yielded %d in window %s..%s",
            examined, yielded, start.isoformat(), end.isoformat(),
        )

    def _parse_paper(
        self,
        paper_id: str,
        url: str,
        html: str,
        start: date,
        end: date,
    ) -> Article | None:
        """Parse one NBER paper HTML page; return an Article or None."""
        # citation_publication_date is YYYY/MM/DD (Google Scholar convention).
        m_date = re.search(
            r'name="citation_publication_date"[^>]+content="(\d{4})/(\d{2})/(\d{2})"',
            html,
        )
        if not m_date:
            return None
        try:
            pub_date = date(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
        except ValueError:
            return None
        if pub_date < start or pub_date > end:
            return None

        m_title = re.search(
            r'name="citation_title"[^>]+content="([^"]+)"', html,
        )
        title = (m_title.group(1) if m_title else "").strip()

        authors: list[str] = re.findall(
            r'name="citation_author"[^>]+content="([^"]+)"', html,
        )
        author = "; ".join(authors) if authors else None

        m_doi = re.search(
            r'name="citation_doi"[^>]+content="([^"]+)"', html,
        )
        doi = m_doi.group(1) if m_doi else None

        m_pdf = re.search(
            r'name="citation_pdf_url"[^>]+content="([^"]+)"', html,
        )
        pdf_url = m_pdf.group(1) if m_pdf else None

        # Body = title + abstract extracted by trafilatura. The abstract
        # is in the main page body on NBER. For papers with no extractable
        # abstract, fall back to title-only.
        try:
            body_text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
            ) or ""
        except Exception:
            body_text = ""
        body = body_text.strip()
        if len(body.split()) < 50:
            # NBER's abstract is sometimes inside a JS-rendered region. Fall
            # back to a structural BS4 lookup for the abstract block.
            try:
                soup = BeautifulSoup(html, "lxml")
                # Common patterns: <div class="page_header_subtitle"> for
                # the citation block; <p> tags inside an article container.
                abstract_p = None
                for header in soup.find_all(["h2", "h3", "strong"]):
                    if header.get_text(strip=True).lower().startswith("abstract"):
                        nxt = header.find_next("p")
                        if nxt:
                            abstract_p = nxt
                            break
                if abstract_p is not None:
                    body = f"{title}\n\n{abstract_p.get_text(strip=True)}"
            except Exception:
                pass
        if not body:
            body = title  # last-resort metadata-only record

        return _make_article(
            source_id=self.source_id,
            url=url,
            published_at=pub_date.isoformat() + "T00:00:00Z",
            title=title or paper_id,
            body=body,
            author=author,
            section="nber_working_paper",
            tier=2,
            document_type="nber_working_paper",
            extra_meta={
                "paper_id": paper_id,
                "doi": doi,
                "pdf_url": pdf_url,
            },
        )


# ---------------------------------------------------------------------------
# Composite ingestor
# ---------------------------------------------------------------------------


class InstitutionalIngestor(Ingestor):
    """Composite: runs all basis-set institutional ingestors.

    ADR-020 (2026-05-20) — basis-set source selection:
      Fed Board + 4 regional Feds + IMF + BIS + CBO + CEA + Treasury OFR +
      Brookings + PIIE + NBER + VoxEU + Congressional Treasury Sec testimony.
      CFR removed (redundant with PIIE on the international-policy dimension).

    Use this as the single entry point for the full Phase 2 semantic corpus
    ingestion.

    Checkpoint/resume: if checkpoint_path is given, a JSON file is written after
    each sub-ingestor completes. On restart, completed sub-ingestors are skipped
    and the JSONL output is opened in append mode by the caller (run_pipeline.py).
    Partial sub-ingestor runs may produce duplicate records; the filter/dedup
    stage handles them.
    """

    source_id = "institutional"

    def __init__(self, checkpoint_path: Path | None = None) -> None:
        self._checkpoint_path = checkpoint_path
        # Order matters for timeout-resume: fast/proven sources first so they
        # checkpoint early, with the two long poles (CBO Wayback enumeration,
        # NBER direct-ID enumeration) last. If the 48h wall is hit mid-run, the
        # resume skips the completed fast sources and reaches the long poles
        # with a fresh wall-clock budget. Yield order has no effect on corpus
        # content (dedup is by URL at the filter stage).
        self._sub_ingestors: list[Ingestor] = [
            FederalReserveIngestor(),
            FedRegionalIngestor(),
            CongressionalIngestor(),
            IMFIngestor(),
            BISIngestor(),
            TreasuryOFRIngestor(),
            CEAIngestor(),
            VoxEUIngestor(),
            BrookingsIngestor(),
            PIIEIngestor(),
            CBOIngestor(),
            NBERIngestor(),
        ]

    def _load_checkpoint(self) -> dict:
        if self._checkpoint_path and self._checkpoint_path.exists():
            try:
                data = json.loads(self._checkpoint_path.read_text())
            except Exception as exc:
                log.warning("Could not load checkpoint %s: %s — starting fresh", self._checkpoint_path, exc)
                return {}
            # Detect false-completed entries (status=completed, count=0) written by
            # the pre-fix bug that treated 0-article fetches as successful completions.
            false_completions = [
                sid for sid, v in data.items()
                if v.get("status") == "completed" and v.get("count", 0) == 0
            ]
            if false_completions:
                genuine_completions = [
                    sid for sid, v in data.items()
                    if v.get("status") == "completed" and v.get("count", 0) > 0
                ]
                if not genuine_completions:
                    # Entire checkpoint is zero-article completions — nothing was ever
                    # successfully fetched. Delete and start completely fresh.
                    log.warning(
                        "Checkpoint %s has no successful fetches (all count=0); deleting and starting fresh",
                        self._checkpoint_path,
                    )
                    self._checkpoint_path.unlink()
                    return {}
                # Some sources genuinely completed; only reset the false ones.
                log.warning(
                    "Checkpoint has %d false-completed sources (count=0): %s — marking failed for retry",
                    len(false_completions), ", ".join(false_completions),
                )
                for sid in false_completions:
                    data[sid] = {"status": "failed", "error": "0 articles on previous run (false completion)"}
                self._save_checkpoint(data)
            return data
        return {}

    def _save_checkpoint(self, data: dict) -> None:
        if self._checkpoint_path:
            self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_path.write_text(json.dumps(data, indent=2))

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        checkpoint = self._load_checkpoint()
        failures: list[tuple[str, str]] = []
        for ingestor in self._sub_ingestors:
            sid = ingestor.source_id
            if checkpoint.get(sid, {}).get("status") == "completed":
                log.info("Checkpoint: skipping %s (already completed, %d articles)",
                         sid, checkpoint[sid].get("count", 0))
                continue
            log.info("InstitutionalIngestor: running %s", sid)
            count = 0
            try:
                for article in ingestor.fetch(start, end):
                    yield article
                    count += 1
                if count > 0:
                    checkpoint[sid] = {"status": "completed", "count": count}
                    self._save_checkpoint(checkpoint)
                    log.info("Checkpoint: %s completed (%d articles)", sid, count)
                else:
                    checkpoint[sid] = {"status": "failed", "error": "returned 0 articles"}
                    self._save_checkpoint(checkpoint)
                    log.warning("Checkpoint: %s returned 0 articles; marked failed for retry", sid)
                    failures.append((sid, "0 articles"))
            except Exception as exc:
                # Record and keep going so ONE run surfaces every broken source
                # (not whack-a-mole), and the sources that DO work still get
                # written + checkpointed. But a fail-loud raise must not let the
                # composite complete clean — re-raise an aggregate below so the
                # process exits non-zero and the afterok downstream chain holds.
                log.error("Sub-ingestor %s failed: %s", sid, exc)
                checkpoint[sid] = {"status": "failed", "error": str(exc)}
                self._save_checkpoint(checkpoint)
                failures.append((sid, str(exc)))
        if failures:
            raise RuntimeError(
                "InstitutionalIngestor: %d/%d sub-ingestor(s) failed; refusing to "
                "complete clean so the downstream chain halts: %s" % (
                    len(failures), len(self._sub_ingestors),
                    ", ".join(f"{s} ({e})" for s, e in failures),
                )
            )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _parse_year_from_text(text: str, start: date, end: date) -> date | None:
    """Extract a 4-digit year from text and return a date if in [start, end]."""
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    for year_str in years:
        year = int(year_str)
        if start.year <= year <= end.year:
            return date(year, 1, 1)
    return None
