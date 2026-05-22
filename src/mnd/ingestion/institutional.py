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
    5. US fiscal authority             CBOIngestor (Playwright + curl_cffi, ADR-017)
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
                dimension. ~80% of CFR output is foreign-policy non-macro;
                the macro subset overlaps PIIE almost completely. Class
                retained in this file (unwired from InstitutionalIngestor)
                so existing data files can be re-read for QA; not run
                in any new ingest.

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
  ArxivIngestor       — 2017-only coverage; archived in scripts/archive/.

Removed (ADR-010):
  AP News, Reuters, MarketWatch journalism tier — archived in scripts/archive/.

All timestamps follow the ADR-008 rule: publication/release date only.
FOMC minutes = release date.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.ingestion.fed import FederalReserveIngestor
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}


def _is_retryable(exc: Exception) -> bool:
    """Retry on server errors and transient network failures; not on 4xx."""
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code >= 500
    return True


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


def _parse_rss(feed_url: str) -> list[feedparser.FeedParserDict]:
    """Fetch and parse an RSS/Atom feed. Returns list of entries."""
    try:
        feed = feedparser.parse(feed_url, request_headers={"User-Agent": USER_AGENT})
        return feed.entries
    except Exception as exc:
        log.warning("RSS parse failed for %s: %s", feed_url, exc)
        return []


def _extract_body(url: str, *, min_words: int = 50) -> str | None:
    """Fetch URL and extract article text with trafilatura. Returns None on failure."""
    try:
        resp = _get(url, timeout=30.0)
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
    except Exception as exc:
        log.debug("Body extraction failed for %s: %s", url, exc)
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


def _fetch_page_full(
    url: str, *, min_words: int = 30, getter=None,
) -> tuple[str, str, str | None, date | None]:
    """Fetch url; return (body_text, title, author, pub_date). Empty/None on failure.

    ``getter`` defaults to module-level _get (stdlib requests + retries). Pass a
    custom callable for sources behind TLS-fingerprint bot protection (e.g.
    CBO behind DataDome — see CBOIngestor._cbo_get).
    """
    fetch = getter if getter is not None else _get
    try:
        resp = fetch(url, timeout=30.0)
    except Exception as exc:
        log.debug("Fetch failed %s: %s", url, exc)
        return "", "", None, None
    try:
        body = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
        meta = trafilatura.extract_metadata(resp.text)
    except Exception:
        body, meta = None, None
    title = (meta.title or "") if meta else ""
    author = (meta.author or None) if meta else None
    pub_date: date | None = None
    if meta and meta.date:
        pub_date = _parse_date_flexible(str(meta.date))
    if not body or len(body.split()) < min_words:
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup.find_all(["nav", "footer", "script", "style", "header"]):
            tag.decompose()
        content = soup.find("main") or soup.find("article") or soup.find("body")
        if content:
            body = content.get_text(separator=" ", strip=True)
    return (body or ""), title, author, pub_date


def _wp_rest_fetch(
    api_base: str,
    post_type: str,
    start: date,
    end: date,
    *,
    extra_fields: str = "link,date,title,excerpt,content",
) -> Iterator[dict]:
    """Yield raw post dicts from a WordPress REST API for the given date range."""
    page = 1
    while True:
        params = {
            "per_page": 100,
            "page": page,
            "after": (start - timedelta(days=1)).isoformat() + "T00:00:00Z",
            "before": (end + timedelta(days=1)).isoformat() + "T00:00:00Z",
            "_fields": extra_fields,
        }
        try:
            resp = requests.get(
                f"{api_base}/wp-json/wp/v2/{post_type}",
                params=params,
                headers=_HEADERS,
                timeout=30.0,
            )
            if resp.status_code in (400, 404):
                break
            resp.raise_for_status()
        except Exception as exc:
            log.warning("WP REST %s/%s page %d: %s", api_base, post_type, page, exc)
            break

        posts = resp.json()
        if not isinstance(posts, list) or not posts:
            break
        yield from posts

        total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            break
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
) -> Article | None:
    """Convert a WP REST API post dict to an Article. Returns None if out of range."""
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
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._IMF_HEADERS)
            return cffi_requests.get(url, **kwargs)
        except ImportError:
            log.error(
                "curl_cffi not installed; IMF fetches will 403. "
                "Install with `pip install curl_cffi` (see requirements.txt / ADR-014)."
            )
            return requests.get(url, **kwargs)

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
                try:
                    body = self._fetch_publication_body(
                        url, build_id, self._IMF_HEADERS
                    )
                except Exception as exc:
                    log.debug("IMF body fetch %s: %s", url, exc)
                    body = None
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
        if resp.status_code != 200:
            log.warning(
                "IMF Coveo HTTP %d for %s [%s..%s]: %s",
                resp.status_code, url_prefix, start, end, resp.text[:300],
            )
            return
        try:
            j = resp.json()
        except Exception as exc:
            log.warning("IMF Coveo JSON parse for %s: %s", url_prefix, exc)
            return

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
            if resp.status_code != 200:
                log.warning(
                    "IMF Coveo page first=%d HTTP %d for %s",
                    first, resp.status_code, url_prefix,
                )
                break
            try:
                j = resp.json()
            except Exception as exc:
                log.warning("IMF Coveo page first=%d JSON parse: %s", first, exc)
                break
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
            return cffi_requests.post(
                endpoint,
                impersonate="chrome131",
                json=body,
                headers=headers,
                timeout=30.0,
            )
        except ImportError:
            log.error(
                "curl_cffi not installed; Coveo POST will likely 401 / 403. "
                "Install with `pip install curl_cffi==0.15.0` (see requirements.txt)."
            )
            return requests.post(
                endpoint, json=body, headers=headers, timeout=30.0,
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

        try:
            resp = self._imf_get(full_url, headers=headers, timeout=30.0)
            if resp.status_code != 200:
                return None
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
            log.debug("IMF HTML body %s: %s", full_url, exc)
        return None


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
        try:
            resp = requests.get(sitemap_url, headers=_HEADERS, timeout=30.0)
            resp.raise_for_status()
            tree = ET.fromstring(resp.content)
        except Exception as exc:
            log.warning("BIS sitemap %d: %s", year, exc)
            return

        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        compiled = [(re.compile(p), s, d) for p, s, d in self._URL_PATTERNS]
        per_section_count: dict[str, int] = {}

        for url_el in tree.findall("s:url", ns):
            loc_el = url_el.find("s:loc", ns)
            mod_el = url_el.find("s:lastmod", ns)
            if loc_el is None:
                continue
            url = loc_el.text or ""

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
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._ATLANTA_HEADERS)
            return cffi_requests.get(url, **kwargs)
        except ImportError:
            log.error(
                "curl_cffi not installed; Atlanta Fed fetches will likely 403. "
                "Install with `pip install curl_cffi` (see requirements.txt)."
            )
            kwargs.setdefault("headers", cls._ATLANTA_HEADERS)
            return requests.get(url, **kwargs)

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        yield from self._fetch_liberty_street(start, end, seen)
        yield from self._fetch_frbsf(start, end, seen)
        yield from self._fetch_chicago_fed_letter(start, end, seen)
        yield from self._fetch_atlanta(start, end, seen)

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
            )
            if article:
                yield article
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
        (r"/publications/insights/(\d{4})/[^/]+$", "insights"),
        (r"/publications/blogs/chicago-fed-insights/(\d{4})/[^/]+$", "insights_blog"),
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
            resp = requests.get(sitemap_url, headers=_HEADERS, timeout=30.0)
            resp.raise_for_status()
            tree = ET.fromstring(resp.content)
        except Exception as exc:
            log.warning("Chicago Fed sitemap failed: %s", exc)
            return

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
            except Exception as exc:
                log.debug("Chicago Fed fetch failed %s: %s", url, exc)
                continue
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
                try:
                    resp = self._atlanta_get(
                        self._ATLANTA_API, params=params, timeout=30.0
                    )
                    status_code = getattr(resp, "status_code", 200)
                    if status_code >= 400:
                        # API errors are loud — these aren't end-of-pagination,
                        # they're upstream failures that should surface in logs.
                        log.error(
                            "Atlanta API %s page=%d HTTP %d (DataSourceId=%s) — "
                            "section will be undercovered",
                            section, page_num, status_code, ds_id,
                        )
                        break
                    text = resp.text or ""
                    if not text.strip():
                        # Empty body is end-of-pagination for a real
                        # query; on page 1 it means no rows match the
                        # window (legitimate when asking working-papers
                        # for a year before the series existed).
                        if page_num == 1:
                            page_zero_status = "empty_response_page_1"
                            log.info(
                                "Atlanta API %s: empty response on page 1 "
                                "(no rows in window %s..%s)",
                                section, api_start, api_end,
                            )
                        break
                    payload = json.loads(text)
                except Exception as exc:
                    log.error(
                        "Atlanta API %s page=%d raised %s: %s",
                        section, page_num, type(exc).__name__, exc,
                    )
                    break

                items_raw = payload.get("FilteredFeedItemsJson") or "[]"
                try:
                    items = json.loads(items_raw)
                except Exception as exc:
                    log.error(
                        "Atlanta API %s page=%d JSON parse failed: %s",
                        section, page_num, exc,
                    )
                    break

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
            try:
                body, fetched_title, author, meta_date = _fetch_page_full(
                    url,
                    min_words=50,
                    getter=lambda u, **kw: self._atlanta_get(u, **kw),
                )
            except Exception as exc:
                log.debug("Atlanta page %s fetch failed: %s", url, exc)
                continue
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

    Network architecture:
      1. CDX query: ``web.archive.org/cdx/search/cdx`` enumerates unique
         cbo.gov/publication/* URLs that have at least one 200/text/html
         snapshot in the requested window. Queries are sharded by year to
         keep result sets under the Wayback rate-limit ceiling (a single
         query for >~5k rows triggers 503). Each query uses
         ``collapse=urlkey`` so we get one (latest) snapshot per publication.
      2. Snapshot fetch: ``web.archive.org/web/{ts}id_/{url}`` — the ``id_``
         modifier returns the raw archived body, no Wayback toolbar rewrite.
         Page-level extraction via the same ``_fetch_page_full`` pipeline
         used elsewhere (trafilatura + BS4 fallback).
      3. Authoritative date: from the page's own structured metadata
         (Drupal's ``<meta name="dcterms.created">`` or trafilatura's date
         extraction). The Wayback snapshot timestamp is the LAST-CRAWLED
         date and is only used as a coarse fallback when the page lacks
         any structured publication date.

    Politeness:
      - 0.5s sleep between CDX shard queries (Wayback rate-limits per minute).
      - 0.3s sleep between snapshot fetches.
      - Exponential backoff retry on Wayback 5xx / 429 — never 403.

    Operational notes:
      - No external dependencies beyond stdlib requests. Playwright and
        curl_cffi are NOT used by this ingestor; both were ineffective
        against cbo.gov's current DataDome policy.
      - The canonical ``url`` field on each emitted Article is the
        cbo.gov publication URL, NOT the Wayback wrapper, so downstream
        dedupe / cluster reporting matches the cbo.gov source-set framing.
      - If DataDome's posture relaxes in the future (or we acquire a paid
        scraping path), the ingestor can be swapped back to cbo.gov direct
        without changing the wrapper signature.
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

    # Wayback CDX rows can be large; shard the requested window by year to
    # stay under the per-query 503 ceiling.
    _CDX_SHARD_YEARS = 1

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        candidates = list(self._enumerate_wayback_candidates(start, end))
        log.info(
            "CBO: Wayback CDX found %d unique cbo.gov/publication/* URLs in "
            "[%s..%s]",
            len(candidates), start, end,
        )
        seen: set[str] = set()
        yielded = 0
        for original_url, snapshot_ts in candidates:
            if original_url in seen:
                continue
            seen.add(original_url)
            snap_url = self._SNAP_PREFIX.format(ts=snapshot_ts, url=original_url)

            body, fetched_title, _author, page_date = _fetch_page_full(
                snap_url, min_words=50, getter=self._wayback_get,
            )
            # Strict date policy (no Wayback-timestamp fallback): the Wayback
            # snapshot timestamp is the last-crawled date, which can be
            # decades after the actual publication date (e.g. a 1993 NAFTA
            # analysis snapshotted in 2023). Such mis-dated records would
            # corrupt the SIR fit. We emit only records whose own page
            # metadata yields a publication date.
            if page_date is None:
                log.debug(
                    "CBO %s: dropped — no page-extracted publication date "
                    "(snapshot_ts=%s)",
                    original_url, snapshot_ts,
                )
                continue
            published = page_date
            if published < start or published > end:
                log.debug(
                    "CBO %s: dropped (page_date=%s out of [%s..%s])",
                    original_url, page_date, start, end,
                )
                continue
            if not body or len(body.split()) < 50:
                log.debug(
                    "CBO %s: body too short (%d words)",
                    original_url, len(body.split()) if body else 0,
                )
                continue
            yield _make_article(
                source_id=self.source_id,
                # Canonical cbo.gov URL — NOT the Wayback wrapper. Keeps the
                # source-set framing on cbo.gov even though retrieval went
                # through the archive.
                url=original_url,
                published_at=published.isoformat() + "T00:00:00Z",
                title=fetched_title or "CBO publication",
                body=body,
                author="CBO",
                section="cbo_publication",
                tier=1,
                document_type="cbo_publication",
            )
            yielded += 1
            time.sleep(0.3)
        if yielded == 0:
            log.warning(
                "CBO: 0 publications from Wayback in [%s..%s]. Either the "
                "window has no archived snapshots or Wayback CDX is failing "
                "(check upstream availability of web.archive.org).",
                start, end,
            )

    # ------------------------------------------------------------------
    # Wayback CDX enumeration
    # ------------------------------------------------------------------

    def _enumerate_wayback_candidates(
        self, start: date, end: date
    ) -> Iterator[tuple[str, str]]:
        """Yield (cbo.gov publication URL, Wayback timestamp YYYYMMDDhhmmss).

        Shards the requested window into year-sized CDX queries to keep
        each result set under the Wayback rate-limiter's 503 ceiling.
        Dedupes URLs across shards (a URL crawled in multiple years yields
        only its earliest in-window snapshot — sufficient since the body
        is the same).
        """
        seen_urls: set[str] = set()
        for shard_start, shard_end in self._year_shards(start, end):
            rows = self._cdx_fetch(shard_start, shard_end)
            for original_url, ts in rows:
                if original_url in seen_urls:
                    continue
                seen_urls.add(original_url)
                yield original_url, ts
            # Polite delay between shards — Wayback rate-limits per minute
            time.sleep(0.5)

    def _year_shards(
        self, start: date, end: date
    ) -> Iterator[tuple[date, date]]:
        """Split [start, end] into ``_CDX_SHARD_YEARS``-year chunks."""
        cur = start
        while cur <= end:
            shard_end = date(cur.year + self._CDX_SHARD_YEARS - 1, 12, 31)
            if shard_end > end:
                shard_end = end
            yield cur, shard_end
            cur = date(shard_end.year + 1, 1, 1)

    def _cdx_fetch(
        self, start: date, end: date, *, max_attempts: int = 4
    ) -> list[tuple[str, str]]:
        """Query Wayback CDX for one shard.

        Returns [(original_url, timestamp), ...]. Retries with exponential
        backoff on 429 / 5xx — Wayback never returns 403 for CDX. Returns
        [] on definitive failure rather than raising; the outer walk keeps
        going across shards.
        """
        params = {
            "url": "cbo.gov/publication/*",
            "from": start.strftime("%Y%m%d"),
            "to": end.strftime("%Y%m%d"),
            "fl": "original,timestamp",
            "filter": ["statuscode:200", "mimetype:text/html"],
            "collapse": "urlkey",
        }
        backoff = 3.0
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.get(
                    self._CDX_API,
                    params=params,
                    headers={"User-Agent": self._UA},
                    timeout=(10, 120),
                )
                if resp.status_code == 200:
                    rows: list[tuple[str, str]] = []
                    for line in resp.text.strip().split("\n"):
                        if not line:
                            continue
                        parts = line.split(" ")
                        if len(parts) < 2:
                            continue
                        original, ts = parts[0], parts[1]
                        if "/publication/" not in original:
                            continue
                        # Drop trailing /html so we hit the canonical URL
                        if original.endswith("/html"):
                            original = original[:-5]
                        rows.append((original, ts))
                    log.debug(
                        "CBO CDX shard %s..%s: %d rows",
                        start, end, len(rows),
                    )
                    return rows
                if resp.status_code in (429, 503):
                    log.debug(
                        "CBO CDX shard %s..%s: HTTP %d (attempt %d/%d) — "
                        "backing off %.1fs",
                        start, end, resp.status_code, attempt, max_attempts,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                log.warning(
                    "CBO CDX shard %s..%s: HTTP %d — giving up on shard",
                    start, end, resp.status_code,
                )
                return []
            except Exception as exc:
                log.debug(
                    "CBO CDX shard %s..%s attempt %d/%d: %s",
                    start, end, attempt, max_attempts, exc,
                )
                time.sleep(backoff)
                backoff *= 2
        log.warning(
            "CBO CDX shard %s..%s: exhausted %d retries — dropping shard",
            start, end, max_attempts,
        )
        return []

    # ------------------------------------------------------------------
    # Wayback snapshot fetcher (passed to _fetch_page_full as ``getter``)
    # ------------------------------------------------------------------

    def _wayback_get(self, url: str, **kwargs):
        """HTTP GET for Wayback snapshot URLs.

        Pass-through wrapper around stdlib requests with a tuple timeout —
        per the lessons of c47fb91, single-value floats only enforce the
        inter-byte read gap; a Wayback edge node dripping bytes never trips
        a 30s single-value timeout.
        """
        timeout = kwargs.pop("timeout", 60.0)
        if isinstance(timeout, (int, float)):
            timeout = (10, max(30, int(timeout)))
        kwargs.setdefault("headers", {"User-Agent": self._UA})
        return requests.get(url, timeout=timeout, **kwargs)

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
    _FSOC_REPORTS = "https://home.treasury.gov/policy-issues/financial-markets-financial-institutions-and-fiscal-service/fsoc/studies-and-reports"

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
            log.warning("OFR index fetch failed %s: %s", index_url, exc)
            return
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

    # FSOC PDF URL pattern: ``/system/files/<id>/fsoc{year}annualreport.pdf`` or
    # ``/system/files/<id>/FSOC{year}AnnualReport.pdf`` (case insensitive). The
    # year is the year the report covers — the Council convention is to publish
    # in the late-Q4 of the same year or in Q1 of the following year. We use
    # December 31 of that year as the publication date floor (authoritative
    # by-year tagging), which matches how downstream weekly-aggregation treats
    # the report's discursive footprint.
    _FSOC_PDF_RE = re.compile(
        r"/system/files/\d+/(?:fsoc|FSOC)[^/]*?(\d{4})[^/]*?annual[^/]*?report[^/]*?\.pdf",
        re.IGNORECASE,
    )

    def _scrape_fsoc(self, start: date, end: date) -> Iterator[Article]:
        """Fetch FSOC annual reports as PDF, extracted to text via pypdf.

        FSOC has published one annual report per year since 2011 (with a
        2010 inaugural). Each is a structured ~200-page PDF surveying
        systemic-risk conditions — a major data point for the financial-
        stability dimension of the basis set. pypdf is mandatory.
        """
        try:
            resp = _get(self._FSOC_REPORTS, timeout=30.0)
        except Exception as exc:
            log.error("FSOC index fetch failed %s: %s", self._FSOC_REPORTS, exc)
            return
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            m = self._FSOC_PDF_RE.search(href)
            if not m:
                continue
            year = int(m.group(1))
            # FSOC publishes annual reports for a calendar year; date the
            # record at the year's December 31 (the report's reporting
            # period closes at year end).
            pub_date = date(year, 12, 31)
            if pub_date < start or pub_date > end:
                continue
            full_url = urljoin("https://home.treasury.gov", href)
            if full_url in seen:
                continue
            seen.add(full_url)
            body = self._extract_pdf_text(full_url)
            if not body or len(body.split()) < 500:
                log.warning(
                    "FSOC %d: PDF extraction yielded %d words (<500 floor) — "
                    "extraction may have failed",
                    year, len(body.split()) if body else 0,
                )
                continue
            title = (link.get_text(strip=True) or
                     f"FSOC Annual Report {year}")
            yield _make_article(
                source_id=self.source_id,
                url=full_url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
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

        Raises ImportError if pypdf is unavailable. A transient fetch or
        parse error returns "" so the caller drops the record but the
        rest of the FSOC walk continues.
        """
        from pypdf import PdfReader
        from io import BytesIO
        try:
            resp = _get(pdf_url, timeout=120.0)
        except Exception as exc:
            log.warning("FSOC PDF fetch %s failed: %s", pdf_url, exc)
            return ""
        try:
            reader = PdfReader(BytesIO(resp.content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(p.strip() for p in pages if p.strip())
        except Exception as exc:
            log.warning("FSOC PDF parse %s failed: %s", pdf_url, exc)
            return ""


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
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._CEPR_HEADERS)
            return cffi_requests.get(url, **kwargs)
        except ImportError:
            log.error(
                "curl_cffi not installed; VoxEU fetches will 403. "
                "Install with `pip install curl_cffi==0.15.0` "
                "(see requirements.txt / ADR-014)."
            )
            return requests.get(url, headers=cls._CEPR_HEADERS, **kwargs)

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
                # First-page failure of a shard means the shard contributes
                # zero records — surface as ERROR so a regression doesn't
                # hide behind a multi-year aggregate. Subsequent-page
                # failures still log ERROR but leave already-collected
                # cards in the yielded set.
                log.error(
                    "VoxEU shard %s..%s page %d: %s — shard truncated at "
                    "%d pages",
                    start, end, page, exc, page,
                )
                return

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
            )
            if article:
                yield article
                time.sleep(1.0)


class PIIEIngestor(Ingestor):
    """Peterson Institute for International Economics: listing page scraper.

    Access pattern (verified 2026-05-21)
    ----------------------------------
    Host: ``piie.com`` is fronted by **Cloudflare**. Listing pages
    sometimes pass a stdlib ``requests`` fetch but individual article
    pages return ``HTTP 403`` with a JS-challenge interstitial
    ("Enable JavaScript and cookies to continue"). The JA3/JA4 TLS
    fingerprint of OpenSSL is the rejection signal — same root cause
    as VoxEU/CEPR (ADR-021) and IMF/Akamai (ADR-014).

    ``curl_cffi`` with ``impersonate='chrome131'`` clears the challenge
    without needing JS execution. Both listing and body fetches are
    routed through ``_piie_get`` so the entire ingest is TLS-impersonated;
    Cloudflare can tighten the listing surface at any time, so it's
    safer to use the impersonating path uniformly.

    The listing covers policy-briefs, working-papers, piie-briefings,
    realtime-economic-issues-watch, and trade-investment-policy-watch.
    Pagination via ``?page=N`` (Drupal default), 10 cards/page.

    Failure mode if curl_cffi missing
    ---------------------------------
    We log an ``error`` and fall back to stdlib ``requests``, which
    will reliably 403 on body fetches — intentional loud failure
    rather than silent zero-yield. ``curl_cffi==0.15.0`` is in
    ``requirements.txt``.

    History
    -------
    - Originally stdlib ``requests`` worked from university IPs because
      PIIE wasn't on Cloudflare. The site enabled Cloudflare bot
      mitigation between ADR-017 (2026-05-19) and 2026-05-21; the
      integration battery on 2026-05-21 surfaced zero PIIE records for
      2023, confirming the regression.
    """

    source_id = "piie"

    _LISTING_PATHS = [
        ("/publications/policy-briefs", "policy_brief"),
        ("/publications/working-papers", "working_paper"),
        ("/publications/piie-briefings", "piie_briefing"),
        ("/blogs/realtime-economic-issues-watch", "blog_post"),
        ("/blogs/trade-investment-policy-watch", "blog_post"),
    ]

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
        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._PIIE_HEADERS)
            return cffi_requests.get(url, **kwargs)
        except ImportError:
            log.error(
                "curl_cffi not installed; PIIE fetches will 403. "
                "Install with `pip install curl_cffi==0.15.0` "
                "(see requirements.txt / ADR-014)."
            )
            return requests.get(url, headers=cls._PIIE_HEADERS, **kwargs)

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for path, doc_type in self._LISTING_PATHS:
            yield from self._fetch_listing(path, doc_type, start, end, seen)

    def _fetch_listing(
        self,
        path: str,
        doc_type: str,
        start: date,
        end: date,
        seen: set[str],
    ) -> Iterator[Article]:
        base = "https://www.piie.com"
        page = 0
        past_window = False
        total_emitted = 0

        while not past_window:
            try:
                resp = self._piie_get(
                    base + path,
                    params={"page": page} if page > 0 else {},
                    timeout=30.0,
                )
                if resp.status_code in (403, 404):
                    log.error(
                        "PIIE %s page %d: HTTP %d — Cloudflare tightening or "
                        "section retired. Section will be undercovered.",
                        path, page, resp.status_code,
                    )
                    return
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}")
            except Exception as exc:
                log.error(
                    "PIIE %s page %d: %s — stopping pagination",
                    path, page, exc,
                )
                return

            soup = BeautifulSoup(resp.text, "lxml")
            # Broader teaser selector — PIIE redesign occasionally swaps
            # <article class="teaser"> for <div class="teaser ..."> on certain
            # listing variants. ".teaser" matches both.
            items = soup.select(".teaser")
            if not items:
                log.info("PIIE %s page %d: 0 teaser items — pagination exhausted",
                         path, page)
                break

            page_in_window = 0
            page_body_failed = 0
            for item in items:
                date_el = item.select_one("time")
                if not date_el:
                    continue
                dt_str = date_el.get("datetime", "")
                try:
                    pub_date = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).date()
                except (ValueError, AttributeError):
                    pub_date = _parse_date_flexible(date_el.get_text(strip=True))
                if not pub_date:
                    continue

                if pub_date > end:
                    continue
                if pub_date < start:
                    past_window = True
                    continue

                page_in_window += 1
                link = item.select_one(".teaser__title a") or item.select_one("h2 a, h3 a")
                if not link:
                    continue
                href = link.get("href", "")
                url = urljoin(base, href) if href.startswith("/") else href
                if url in seen:
                    continue
                seen.add(url)

                title = link.get_text(strip=True)
                author_el = item.select_one(".author-list")
                author = author_el.get_text(" ", strip=True) if author_el else None

                # Fetch full body. ADR-016: ingest is content-neutral and there
                # is NO Stage 1 topic filter; we either capture the article
                # body or skip the record (do not emit title-only fallbacks
                # that would carry no body signal for Stage 2 to evaluate).
                # Body fetch routes through _piie_get so it bypasses the
                # Cloudflare JS challenge that defeats stdlib requests.
                body, fetched_title, _, _pd = _fetch_page_full(
                    url, min_words=50, getter=self._piie_get,
                )
                if fetched_title and not title:
                    title = fetched_title
                if not body or len(body.split()) < 50:
                    page_body_failed += 1
                    log.debug("PIIE body unavailable / too short for %s", url)
                    continue

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author=author,
                    section="piie_publication",
                    tier=2,
                    document_type=f"piie_{doc_type}",
                )
                total_emitted += 1
                time.sleep(1.0)

            log.info(
                "PIIE %s page %d: %d items, %d in-window, %d body-failed, %d emitted "
                "(running total: %d)",
                path, page, len(items), page_in_window, page_body_failed,
                page_in_window - page_body_failed, total_emitted,
            )
            page += 1
            time.sleep(0.5)


class CFRIngestor(Ingestor):
    """Council on Foreign Relations: sitemap-based historical retrieval.

    CFR publishes reports, backgrounders, and expert briefs on global macro-
    financial topics: dollar dynamics, sovereign debt, global monetary policy,
    trade, and geopolitical-financial intersections. Tier 2 per ADR-010.

    Pre-fix bug (2026-05-13 dry run, 0 articles): the RSS feed at
    cfr.org/feed exposes only the most recent ~24 items, giving zero
    coverage for any historical window. Fixed by switching to sitemap-based
    enumeration of /articles, /backgrounders, /reports — each sitemap is
    public and lists every URL with a `<lastmod>` date.

    Coverage: sitemaps return ~22,000 articles + ~1,000 backgrounders +
    ~700 reports as of 2026-05. URL-slug pre-filter on macro keywords
    avoids fetching every irrelevant article. RSS is retained as a final
    fallback.
    """

    source_id = "cfr"

    _SITEMAP_INDEX = "https://www.cfr.org/sitemap.xml"
    # CFR-content sitemap sections we ingest. Skipping experts/, events/,
    # podcasts/, custom-links/, interactive/, explainer-videos/ — these are
    # not the long-form policy text we embed.
    _RELEVANT_SECTIONS = ("articles", "backgrounders", "reports")
    _RSS_URL = "https://www.cfr.org/feed"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        candidates = list(self._enumerate_sitemap_candidates(start, end))
        log.info("CFR: sitemap enumeration returned %d in-window candidates "
                 "(structural section filter only; no topic pre-filter)",
                 len(candidates))
        yielded = 0
        for url, pub_date in candidates:
            if url in seen:
                continue
            seen.add(url)
            body, fetched_title, author, page_date = _fetch_page_full(
                url, min_words=50
            )
            published = page_date or pub_date
            if not published or published < start or published > end:
                continue
            title = fetched_title or ""
            # ADR-016: no Stage 1 topic filter — content-neutral ingest.
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=published.isoformat() + "T00:00:00Z",
                title=title or "CFR publication",
                body=body,
                author=author,
                section="cfr_publication",
                tier=2,
                document_type="cfr_brief",
            )
            yielded += 1
            time.sleep(0.5)

        if yielded == 0:
            log.info("CFR: 0 articles from sitemap path — falling back to RSS")
            yield from self._fetch_rss(start, end, seen)

    def _enumerate_sitemap_candidates(
        self, start: date, end: date
    ) -> Iterator[tuple[str, date | None]]:
        """Walk the CFR sitemap index, yielding (url, lastmod) for URLs in
        relevant sections with a macro-keyword in the slug and lastmod in
        the requested window.
        """
        try:
            resp = requests.get(self._SITEMAP_INDEX, headers=_HEADERS, timeout=30.0)
            resp.raise_for_status()
        except Exception as exc:
            log.warning("CFR sitemap index fetch failed: %s", exc)
            return

        try:
            index_xml = re.sub(r' xmlns="[^"]+"', "", resp.text, count=1)
            root = ET.fromstring(index_xml)
        except ET.ParseError as exc:
            log.warning("CFR sitemap index parse failed: %s", exc)
            return

        sub_sitemaps = [sm.findtext("loc", "").strip() for sm in root.findall("sitemap")]
        relevant = [
            s for s in sub_sitemaps
            if any(f"/{section}/" in s for section in self._RELEVANT_SECTIONS)
        ]
        log.info("CFR sitemap index lists %d sub-sitemaps; %d relevant",
                 len(sub_sitemaps), len(relevant))

        for sm_url in relevant:
            try:
                sm_resp = requests.get(sm_url, headers=_HEADERS, timeout=30.0)
                sm_resp.raise_for_status()
            except Exception as exc:
                log.debug("CFR sub-sitemap %s: %s", sm_url, exc)
                continue
            try:
                sm_xml = re.sub(r' xmlns="[^"]+"', "", sm_resp.text, count=1)
                sm_root = ET.fromstring(sm_xml)
            except ET.ParseError as exc:
                log.debug("CFR sub-sitemap %s parse: %s", sm_url, exc)
                continue
            section_count = 0
            section_yielded = 0
            for url_el in sm_root.findall("url"):
                section_count += 1
                loc = (url_el.findtext("loc") or "").strip()
                if not loc:
                    continue
                # NOTE: CFR's sitemap lastmod is the sitemap-build date (all
                # 2026-XX-XX as of 2026-05) — not the publication date. We
                # drop the lastmod window check and rely on the page-level
                # date extracted by _fetch_page_full to filter into window.
                # ADR-016: no URL-slug topic pre-filter either — section-level
                # filter (_RELEVANT_SECTIONS) is the only structural gate;
                # topic relevance is decided at Stage 2 over title+body.
                section_yielded += 1
                yield loc, None
            log.info("CFR sitemap %s: %d urls in section (no topic pre-filter)",
                     sm_url.rsplit("/", 2)[-2], section_count)
            time.sleep(0.3)

    def _fetch_rss(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        for entry in _parse_rss(self._RSS_URL):
            pub_date = _entry_date(entry)
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url or url in seen:
                continue
            title = entry.get("title", "")
            # ADR-016: no Stage 1 topic filter.
            seen.add(url)

            body = _extract_body(url) or BeautifulSoup(
                entry.get("summary", ""), "lxml"
            ).get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue

            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author=entry.get("author"),
                section="cfr_publication",
                tier=2,
                document_type="cfr_brief",
            )
            time.sleep(1.0)


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
                    timeout=30.0,
                )
                if resp.status_code in (403, 404):
                    log.error("Treasury listing page %d: HTTP %d — aborting", page, resp.status_code)
                    return
                resp.raise_for_status()
            except Exception as exc:
                log.error("Treasury listing page %d: %s — aborting", page, exc)
                return

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
            f"?api_key={api_key}&pageSize=100&offsetMark=*"
        )
        offset = "*"
        page = 0
        while True:
            page += 1
            paged_url = re.sub(r"offsetMark=[^&]+", f"offsetMark={offset}", url)
            try:
                resp = _get(paged_url, timeout=60.0)
                data = resp.json()
            except Exception as exc:
                log.warning("Congressional CHRG package list (page %d): %s", page, exc)
                return
            packages = data.get("packages", [])
            if not packages:
                return
            for pkg in packages:
                yield pkg
            next_offset = data.get("nextPage") or data.get("offsetMark")
            if not next_offset or next_offset == offset:
                return
            offset = next_offset
            time.sleep(1.0)
            # Safety bound. CHRG has ~3000 hearings/year × 16 years = 48k
            # packages at pageSize=100 = ~480 pages. Bail at 1000 to avoid
            # an infinite loop if the API contract drifts.
            if page > 1000:
                log.warning("Congressional CHRG package list exceeded 1000 pages — bailing")
                return

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
            f"?api_key={api_key}&pageSize=100&offsetMark=*"
        )
        offset = "*"
        page = 0
        while True:
            page += 1
            paged_url = re.sub(r"offsetMark=[^&]+", f"offsetMark={offset}", url)
            try:
                resp = _get(paged_url, timeout=60.0)
                data = resp.json()
            except Exception as exc:
                log.warning("CEA package list fetch failed (page %d): %s", page, exc)
                return
            packages = data.get("packages", [])
            if not packages:
                return
            for pkg in packages:
                yield pkg
            next_offset = data.get("nextPage") or data.get("offsetMark")
            # offsetMark in the response is the next cursor; if absent, stop.
            if not next_offset or next_offset == offset:
                return
            offset = next_offset
            time.sleep(0.5)
            # Safety bound — ERP has ~61 packages historical; should fit in
            # one or two pages. Bail at 10 pages to avoid an infinite loop
            # if the API contract drifts.
            if page > 10:
                log.warning("CEA package list exceeded 10 pages — bailing")
                return

    def _fetch_granules(
        self, api_key: str, package_id: str, issued: date,
    ) -> Iterator[Article]:
        """Yield one Article per chapter-level granule of one ERP package."""
        url = (
            f"{self._GOVINFO_BASE}/packages/{package_id}/granules"
            f"?api_key={api_key}&pageSize=200&offsetMark=*"
        )
        try:
            resp = _get(url, timeout=60.0)
            data = resp.json()
        except Exception as exc:
            log.warning("CEA granule list %s failed: %s", package_id, exc)
            return
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
    def _extract_pdf_text(pdf_url: str) -> str:
        """Download a PDF and return its extracted text.

        Raises ImportError if pypdf is unavailable — CEA cannot operate
        without it. A transient PDF fetch / parse error returns "" so
        the caller drops the granule but the rest of the ingest proceeds.
        """
        from pypdf import PdfReader
        from io import BytesIO
        try:
            resp = _get(pdf_url, timeout=60.0)
        except Exception as exc:
            log.debug("CEA PDF fetch %s failed: %s", pdf_url, exc)
            return ""
        try:
            reader = PdfReader(BytesIO(resp.content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(p.strip() for p in pages if p.strip())
        except Exception as exc:
            log.debug("CEA PDF parse %s failed: %s", pdf_url, exc)
            return ""

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
    # walked past the head of the series.
    _STOP_AFTER_CONSECUTIVE_404S = 30

    # NBER publishes ~1500 working papers per year. Per-year buffer beyond
    # the latest calibrated floor that we'll probe before relying on the
    # consecutive-404 termination signal to stop enumeration. Generous
    # margin so a high-volume year doesn't run off the end of the table.
    _ID_HEADROOM_PER_FORECAST_YEAR = 2500

    def _compute_ceiling(self, end_year: int) -> int:
        """Compute the upper paper-ID bound for an enumeration.

        Prefer the calibrated next-year floor when present; otherwise
        project forward from the latest calibrated year using a per-year
        headroom. The consecutive-404 stop (line below) prevents wasted
        requests once we walk past the head of the series, so the ceiling
        only needs to be ``>=`` the true head.
        """
        if (next_year_floor := self._PAPER_FLOOR_BY_YEAR.get(end_year + 1)):
            return next_year_floor
        latest_year = max(self._PAPER_FLOOR_BY_YEAR)
        latest_floor = self._PAPER_FLOOR_BY_YEAR[latest_year]
        years_forward = max(1, end_year - latest_year + 1)
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
                log.debug("NBER %s HTTP %s: %s", paper_id, status, exc)
                continue
            except Exception as exc:
                log.debug("NBER %s fetch failed: %s", paper_id, exc)
                continue
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
        self._sub_ingestors: list[Ingestor] = [
            FederalReserveIngestor(),
            FedRegionalIngestor(),
            CongressionalIngestor(),
            IMFIngestor(),
            BISIngestor(),
            TreasuryOFRIngestor(),
            CBOIngestor(),
            CEAIngestor(),
            VoxEUIngestor(),
            BrookingsIngestor(),
            PIIEIngestor(),
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
            except Exception as exc:
                log.error("Sub-ingestor %s failed: %s", sid, exc)
                checkpoint[sid] = {"status": "failed", "error": str(exc)}
                self._save_checkpoint(checkpoint)


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
