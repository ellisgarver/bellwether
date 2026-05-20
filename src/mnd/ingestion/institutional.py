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
            if pub_date is None:
                pub_date = date(year, 1, 1)

            if pub_date < start or pub_date > end:
                continue
            if url in seen:
                continue
            seen.add(url)

            body, title, author, _ = _fetch_page_full(url, min_words=50)
            if not body or len(body.split()) < 50:
                continue

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
      Atlanta Fed publications — sitemap walk via curl_cffi (atlantafed.org
        bot-protects stdlib `requests`) across working papers, policy hub,
        macroblog, and economy matters; RSS fallback for the macroblog.

    The main FederalReserveIngestor (fed.py) covers Board communications.
    This ingestor captures regional analytical content.
    """

    source_id = "fed_regional"

    _ATLANTA_RSS = "https://www.atlantafed.org/blogs/macroblog/rss"
    _ATLANTA_SITEMAP = "https://www.atlantafed.org/sitemap.xml"

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

    # Atlanta Fed publication URL patterns. Captures from sitemap walk.
    # The `(\d{4})` group captures year for window filtering.
    _ATLANTA_URL_PATTERNS: list[tuple[str, str]] = [
        (r"/research/publications/wp/(\d{4})/", "working_paper"),
        (r"/research/publications/policy-hub/(\d{4})/", "policy_hub"),
        (r"/blogs/macroblog/(\d{4})/", "macroblog"),
        (r"/economy-matters/[a-z\-/]*?/(\d{4})/", "economy_matters"),
    ]

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

            body, title, author, meta_date = _fetch_page_full(url, min_words=50)
            if not body or len(body.split()) < 50:
                continue

            # URL year is reliable (publications are year-numbered).
            # trafilatura's meta_date sometimes returns the page-modified
            # date (today) instead of publication date — accept it only when
            # it agrees with the URL year. Otherwise mid-year is a safer
            # fallback than Jan 1 for weekly aggregation.
            pub_date = date(year, 6, 15)
            if meta_date and meta_date.year == year:
                pub_date = meta_date

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
        """Walk atlantafed.org sitemap across working papers, policy hub,
        macroblog, and economy matters; fall back to macroblog RSS.

        Prior code used only the macroblog RSS, which (a) covers ~30 days,
        (b) was returning 403 on RCC because atlantafed.org bot-protects
        stdlib `requests`. Result: 0 atlanta records in the production
        corpus.

        Sitemap discovery via curl_cffi reaches the full working-paper
        archive (~150 papers/year × 15 years) and the policy hub backlog.
        Macroblog historical content (pre-2022) was removed during the
        site redesign; recent macroblog posts come from the sitemap if
        present, otherwise RSS.
        """
        yielded_from_sitemap = 0

        try:
            resp = self._atlanta_get(self._ATLANTA_SITEMAP, timeout=30.0)
            if getattr(resp, "status_code", 200) >= 400:
                raise RuntimeError(f"sitemap HTTP {resp.status_code}")
            tree = ET.fromstring(resp.content)
        except Exception as exc:
            log.warning("Atlanta Fed sitemap fetch failed: %s — will fall back to RSS", exc)
            tree = None

        if tree is not None:
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            # Handle both flat sitemap and sitemap index.
            child_sitemaps: list[str] = [
                (s.findtext("s:loc", default="", namespaces=ns) or "")
                for s in tree.findall("s:sitemap", ns)
            ]
            if not child_sitemaps:
                child_sitemaps = [self._ATLANTA_SITEMAP]
            else:
                child_sitemaps = [s for s in child_sitemaps if s]

            compiled = [(re.compile(p), s) for p, s in self._ATLANTA_URL_PATTERNS]
            candidate_urls: list[tuple[str, int, str]] = []  # (url, year, section)

            for sm in child_sitemaps:
                try:
                    if sm == self._ATLANTA_SITEMAP:
                        sub_tree = tree
                    else:
                        sub_resp = self._atlanta_get(sm, timeout=30.0)
                        sub_tree = ET.fromstring(sub_resp.content)
                except Exception as exc:
                    log.debug("Atlanta child sitemap %s failed: %s", sm, exc)
                    continue
                for url_el in sub_tree.findall("s:url", ns):
                    loc = url_el.findtext("s:loc", default="", namespaces=ns) or ""
                    if not loc:
                        continue
                    for pat, section in compiled:
                        m = pat.search(loc)
                        if not m:
                            continue
                        try:
                            year = int(m.group(1))
                        except ValueError:
                            continue
                        if year < start.year or year > end.year:
                            break
                        candidate_urls.append((loc, year, section))
                        break

            for url, year, section in candidate_urls:
                if url in seen:
                    continue
                seen.add(url)
                try:
                    page = self._atlanta_get(url, timeout=30.0)
                    if getattr(page, "status_code", 200) >= 400:
                        log.debug("Atlanta page %s: HTTP %s", url, page.status_code)
                        continue
                    body, title, author, meta_date = _fetch_page_full(
                        url, min_words=50,
                        getter=lambda u, **kw: self._atlanta_get(u, **kw),
                    )
                except Exception as exc:
                    log.debug("Atlanta page %s fetch failed: %s", url, exc)
                    continue
                if not body or len(body.split()) < 50:
                    continue
                pub_date = meta_date if (meta_date and meta_date.year == year) else date(year, 6, 15)
                if pub_date < start or pub_date > end:
                    continue
                yield _make_article(
                    source_id="fed_atlanta",
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title or f"Atlanta Fed {section.replace('_',' ').title()} {year}",
                    body=body,
                    author=author,
                    section=section,
                    tier=1,
                    document_type="fed_regional_research",
                )
                yielded_from_sitemap += 1
                time.sleep(0.5)

        if yielded_from_sitemap == 0:
            log.info(
                "Atlanta Fed: 0 articles from sitemap walk — falling back to "
                "macroblog RSS (recent content only)."
            )
            for entry in _parse_rss(self._ATLANTA_RSS):
                pub_date = _entry_date(entry)
                if not pub_date or pub_date < start or pub_date > end:
                    continue
                url = entry.get("link", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                title = entry.get("title", "Atlanta Fed macroblog")
                body = _extract_body(url) or BeautifulSoup(
                    entry.get("summary", ""), "lxml"
                ).get_text(strip=True)
                if not body or len(body.split()) < 50:
                    continue
                yield _make_article(
                    source_id="fed_atlanta",
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author=entry.get("author"),
                    section="macroblog",
                    tier=1,
                    document_type="fed_regional_research",
                    extra_meta={"historical_gap": True},
                )
                time.sleep(0.5)


class CBOIngestor(Ingestor):
    """Congressional Budget Office publications.

    Network: every cbo.gov publication-page fetch goes through
    ``curl_cffi.requests`` with ``impersonate='chrome131'``. cbo.gov sits
    behind DataDome bot protection that fingerprints TLS (JA3/JA4) and 403s
    stdlib `requests` regardless of UA — the same class of issue ADR-014
    solved for imf.org behind Akamai. The 2026-05-18 production run with
    stdlib requests yielded 0 publications out of 25,403 candidate URLs
    (every fetch 403'd from the RCC IP range, despite an earlier dry-run
    succeeding before DataDome tightened its policy).

    ADR-017 fix (2026-05-19): Playwright launches a real headless Chromium
    once per ingest run to clear DataDome's JS execution challenge and
    capture the resulting clearance cookies (~3-5s). Those cookies are then
    reused across all curl_cffi fetches for the duration of the ingest —
    avoiding the per-URL browser overhead that would make a 25k-URL walk
    impractical. On a burst of 403s mid-walk, cookies are invalidated and
    re-acquired (up to 3 times) so a rotated DataDome session doesn't
    abort the job. Requires ``pip install playwright && playwright install
    chromium`` in the conda env on RCC.

    Listing path: cbo.gov's sitemap.xml is NOT bot-protected and returns
    200 from any UA. We walk the sitemap index to enumerate candidate
    publication URLs in the requested window, then fetch each publication
    page via curl_cffi-with-cookies.

    `lastmod` is the last-edit date, not publication date — CBO occasionally
    edits prior publications. We add a ±365-day slop to the window when
    filtering by lastmod, then re-validate the publication date extracted
    from the page itself (which is the source of truth for `published_at`).
    """

    source_id = "cbo"

    _SITEMAP_INDEX = "https://www.cbo.gov/sitemap.xml"
    _LIST_URL = "https://www.cbo.gov/publications"
    _RSS_URL = "https://www.cbo.gov/publication/rss"
    _CBO_BASE = "https://www.cbo.gov"

    # Full Chrome navigation header set + curl_cffi TLS fingerprint together
    # defeat DataDome's bot filter. UA alone or TLS alone is rejected.
    _CBO_HEADERS: dict = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
    }

    # Class-level cookie cache: DataDome clearance cookie acquired via
    # Playwright is reused across all subsequent curl_cffi fetches until
    # invalidated (e.g. after a 403). Acquiring the cookie launches a real
    # Chromium browser, waits for DataDome's JS challenge to complete, then
    # extracts the resulting cookie jar. The cookie is typically valid for
    # hours, so one acquisition amortizes across tens of thousands of fetches.
    _cookie_cache: dict[str, str] = {}
    _cookie_acquired_at: float = 0.0

    @classmethod
    def _acquire_cookies(cls) -> bool:
        """Launch headless Chromium, visit cbo.gov, capture DataDome clearance cookie.

        Returns True if cookies were acquired (or already cached), False on
        failure (Playwright not installed, Chromium not available, challenge
        timed out). On failure, callers fall through to curl_cffi-only fetches
        which will 403 — surfacing the failure rather than degrading silently.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error(
                "Playwright not installed — cannot acquire DataDome cookies for cbo.gov. "
                "Install with `pip install playwright && playwright install chromium`."
            )
            return False

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent=cls._CBO_HEADERS["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                )
                page = ctx.new_page()
                # Visit homepage — triggers DataDome challenge if any.
                page.goto(cls._CBO_BASE + "/", wait_until="networkidle", timeout=45000)
                # Visit a publication URL — confirms challenge cleared and
                # the cookie is valid for the publication path.
                page.goto(cls._CBO_BASE + "/publications", wait_until="networkidle", timeout=45000)
                cookies = ctx.cookies(cls._CBO_BASE)
                browser.close()
            jar = {c["name"]: c["value"] for c in cookies}
            if not jar:
                log.error("Playwright session for cbo.gov produced no cookies")
                return False
            cls._cookie_cache = jar
            cls._cookie_acquired_at = time.time()
            log.info("Acquired %d cookies for cbo.gov (Playwright); names: %s",
                     len(jar), ",".join(sorted(jar)[:5]))
            return True
        except Exception as exc:
            log.error("Playwright cookie acquisition for cbo.gov failed: %s", exc)
            return False

    @classmethod
    def _cbo_get(cls, url: str, **kwargs):
        """HTTP GET for cbo.gov URLs.

        Layered defense against DataDome bot protection:
          1. First use call triggers a Playwright session to obtain a fresh
             DataDome clearance cookie (~3-5s, one-time per ingest run).
          2. Every subsequent fetch is a fast curl_cffi GET with Chrome TLS
             impersonation AND the Playwright-acquired cookies — no per-URL
             browser overhead.

        If Playwright isn't installed or the challenge fails, falls through to
        cookie-less curl_cffi which will 403 — surfacing the failure loudly
        rather than producing another silent 0-yield run.
        """
        # Acquire cookies on first call. Re-acquire if the cache is empty
        # (e.g. a previous 403 invalidated them).
        if not cls._cookie_cache:
            cls._acquire_cookies()

        try:
            from curl_cffi import requests as cffi_requests
            kwargs.setdefault("impersonate", "chrome131")
            kwargs.setdefault("headers", cls._CBO_HEADERS)
            if cls._cookie_cache:
                kwargs.setdefault("cookies", dict(cls._cookie_cache))
            return cffi_requests.get(url, **kwargs)
        except ImportError:
            log.error(
                "curl_cffi not installed; CBO fetches will 403 from DataDome. "
                "Install with `pip install curl_cffi` (see requirements.txt)."
            )
            kwargs.setdefault("headers", cls._CBO_HEADERS)
            if cls._cookie_cache:
                kwargs.setdefault("cookies", dict(cls._cookie_cache))
            return requests.get(url, **kwargs)

    @classmethod
    def _invalidate_cookies(cls) -> None:
        """Drop cached cookies — forces re-acquisition on next _cbo_get call.

        Triggered by the fail-fast 403 path inside fetch() so a rotated
        DataDome session can be re-acquired mid-walk without aborting.
        """
        cls._cookie_cache = {}
        cls._cookie_acquired_at = 0.0

    # Slop applied to lastmod window — CBO edits older publications, and
    # they appear to do periodic sitemap-wide rebuilds (~6000 items show
    # lastmod=2019 from one such event). 365 days catches edited pubs from
    # neighboring years; the page-date filter inside fetch() is the final
    # truth. For a full 2010-2026 historical run the slop is moot.
    _LASTMOD_SLOP_DAYS = 365

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        yielded = 0
        candidates = list(self._enumerate_sitemap_candidates(start, end))
        log.info(
            "CBO: sitemap enumeration found %d candidate publication URLs "
            "with lastmod in [%s ± %dd]",
            len(candidates), f"{start}..{end}", self._LASTMOD_SLOP_DAYS,
        )
        consecutive_403s = 0
        cookie_reacquire_attempts = 0
        for url, _lastmod in candidates:
            if url in seen:
                continue
            seen.add(url)
            # 403 recovery: after N consecutive 403s, invalidate the cached
            # DataDome cookies and re-acquire via Playwright (ADR-017). Cookies
            # rotate periodically; this lets us recover mid-walk without
            # restarting the SLURM job. After K failed re-acquisitions, give up.
            if consecutive_403s >= 50:
                if cookie_reacquire_attempts < 3:
                    cookie_reacquire_attempts += 1
                    log.warning(
                        "CBO: %d consecutive 403s — invalidating cached cookies "
                        "and re-acquiring via Playwright (attempt %d/3)",
                        consecutive_403s, cookie_reacquire_attempts,
                    )
                    type(self)._invalidate_cookies()
                    if type(self)._acquire_cookies():
                        consecutive_403s = 0
                        # Retry this URL once with fresh cookies.
                        seen.discard(url)
                        continue
                    log.warning("CBO: cookie re-acquisition failed — continuing")
                else:
                    log.warning(
                        "CBO: %d consecutive 403s after %d cookie re-acquisitions "
                        "— aborting sitemap walk. DataDome blocking definitively. "
                        "Treated as known coverage gap.",
                        consecutive_403s, cookie_reacquire_attempts,
                    )
                    break
            try:
                resp = self._cbo_get(url, timeout=30.0)
                if resp.status_code == 403:
                    consecutive_403s += 1
                    log.debug("CBO %s: HTTP 403 — skipping (consecutive: %d)", url, consecutive_403s)
                    continue
                if resp.status_code == 404:
                    consecutive_403s = 0
                    log.debug("CBO %s: HTTP 404 — skipping", url)
                    continue
                resp.raise_for_status()
                consecutive_403s = 0
            except Exception as exc:
                log.debug("CBO %s: %s", url, exc)
                continue

            body, fetched_title, _author, page_date = _fetch_page_full(
                url, min_words=50, getter=self._cbo_get,
            )
            # Fall back to lastmod ONLY if page date missing — better than dropping
            published = page_date or _lastmod
            if not published or published < start or published > end:
                continue
            title = fetched_title or ""
            # ADR-016: no Stage 1 topic filter. Single canonical topic filter
            # operates at Stage 2 over title+body, where the body provides the
            # signal a title-only filter would miss asymmetrically.
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=published.isoformat() + "T00:00:00Z",
                title=title or "CBO publication",
                body=body,
                author="CBO",
                section="cbo_publication",
                tier=1,
                document_type="cbo_publication",
            )
            yielded += 1
            time.sleep(0.5)

        if yielded == 0:
            # ADR-016: do not introduce source-specific fallback paths (Wayback
            # snapshots, third-party mirrors) just to close one gap. CBO is a
            # documented coverage gap until cbo.gov direct retrieval works.
            # Legacy archive + RSS scrapes are retained ONLY for recent
            # content; they share the same DataDome backend and typically
            # fail too, but cost is bounded.
            log.warning(
                "CBO: 0 publications from cbo.gov (DataDome-blocked). "
                "Trying legacy archive + RSS — recent items only if they "
                "happen to slip past DataDome. Documented coverage gap."
            )
            for article in self._fetch_archive(start, end, seen):
                yield article
                yielded += 1
            if yielded == 0:
                yield from self._fetch_rss(start, end, seen)

    def _enumerate_sitemap_candidates(
        self, start: date, end: date
    ) -> Iterator[tuple[str, date | None]]:
        """Walk the sitemap index, return (url, lastmod) for in-window publications.

        Yields URLs whose lastmod is within [start - SLOP, end + SLOP]. Final
        date validation happens via the publication page itself.
        """
        slop = timedelta(days=self._LASTMOD_SLOP_DAYS)
        lo, hi = start - slop, end + slop
        try:
            resp = self._cbo_get(self._SITEMAP_INDEX, timeout=30.0)
            resp.raise_for_status()
        except Exception as exc:
            log.warning("CBO sitemap index fetch failed: %s", exc)
            return

        try:
            # Strip default-namespace so xpath-like access is simpler
            index_xml = re.sub(r' xmlns="[^"]+"', "", resp.text, count=1)
            root = ET.fromstring(index_xml)
        except ET.ParseError as exc:
            log.warning("CBO sitemap index parse failed: %s", exc)
            return

        sub_sitemaps = [sm.findtext("loc", "").strip() for sm in root.findall("sitemap")]
        sub_sitemaps = [s for s in sub_sitemaps if s]
        log.info("CBO sitemap index lists %d sub-sitemaps", len(sub_sitemaps))

        for sm_url in sub_sitemaps:
            try:
                sm_resp = self._cbo_get(sm_url, timeout=30.0)
                sm_resp.raise_for_status()
            except Exception as exc:
                log.debug("CBO sub-sitemap %s: %s", sm_url, exc)
                continue
            try:
                sm_xml = re.sub(r' xmlns="[^"]+"', "", sm_resp.text, count=1)
                sm_root = ET.fromstring(sm_xml)
            except ET.ParseError as exc:
                log.debug("CBO sub-sitemap %s parse: %s", sm_url, exc)
                continue
            for url_el in sm_root.findall("url"):
                loc = (url_el.findtext("loc") or "").strip()
                lastmod_str = (url_el.findtext("lastmod") or "").strip()
                if not loc or "/publication/" not in loc:
                    continue
                # Normalize: drop trailing /html so we hit the canonical URL
                if loc.endswith("/html"):
                    loc = loc[:-5]
                lastmod = None
                if lastmod_str:
                    try:
                        lastmod = date.fromisoformat(lastmod_str[:10])
                    except ValueError:
                        pass
                if lastmod is None or lo <= lastmod <= hi:
                    yield loc, lastmod
            time.sleep(0.2)

    def _fetch_archive(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        """Legacy archive scrape — Drupal listing at cbo.gov/publications.

        Kept as a fallback; expected to fail under DataDome bot protection.
        """
        page = 0
        past_window = False
        while not past_window:
            try:
                resp = self._cbo_get(
                    self._LIST_URL,
                    params={"page": page},
                    timeout=30.0,
                )
                if resp.status_code == 403:
                    log.debug("CBO publications blocked (HTTP 403) — skipping archive")
                    return
                resp.raise_for_status()
            except Exception as exc:
                log.warning("CBO archive page %d: %s", page, exc)
                return

            soup = BeautifulSoup(resp.text, "lxml")
            rows = (
                soup.select(".views-row")
                or soup.select("li.views-row")
                or soup.select("article")
                or soup.select(".pub-listing-item")
            )
            if not rows:
                break

            for row in rows:
                link = row.find("a", href=True)
                if not link:
                    continue
                href = link["href"]
                url = urljoin(self._CBO_BASE, href)
                title = link.get_text(strip=True)

                date_el = row.find("time") or row.find(class_=lambda c: c and "date" in c.lower() if c else False)
                date_text = date_el.get("datetime", "") or (date_el.get_text(strip=True) if date_el else "")
                pub_date = _parse_date_flexible(date_text)
                if not pub_date:
                    pub_date = _parse_year_from_text(row.get_text(" ", strip=True), start, end)
                if not pub_date:
                    continue

                if pub_date > end:
                    continue
                if pub_date < start:
                    past_window = True
                    continue

                # ADR-016: no Stage 1 topic filter.
                if url in seen:
                    continue
                seen.add(url)

                body = _extract_body(url, min_words=50)
                if not body or len(body.split()) < 50:
                    continue

                yield _make_article(
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    title=title,
                    body=body,
                    author="CBO",
                    section="cbo_publication",
                    tier=1,
                    document_type="cbo_publication",
                )
                time.sleep(1.0)

            page += 1
            time.sleep(0.5)

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
            seen.add(url)
            title = entry.get("title", "CBO publication")
            # ADR-016: no Stage 1 topic filter.
            body = _extract_body(url) or BeautifulSoup(entry.get("summary", ""), "lxml").get_text(strip=True)
            if not body or len(body.split()) < 50:
                continue
            yield _make_article(
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                title=title,
                body=body,
                author="CBO",
                section="cbo_publication",
                tier=1,
                document_type="cbo_publication",
            )
            time.sleep(0.5)



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

    def _scrape_fsoc(self, start: date, end: date) -> Iterator[Article]:
        # FSOC Annual Reports are PDF-only — no extractable HTML body.
        # Skip silently; they are documented as a corpus limitation.
        log.debug("FSOC Annual Reports are PDF-only; skipping for text corpus")
        return
        yield  # make this a generator


# ---------------------------------------------------------------------------
# Tier 2 — Academic analytical
# ---------------------------------------------------------------------------


class VoxEUIngestor(Ingestor):
    """VoxEU / CEPR columns: date-filtered archive search, sharded by year.

    Hits the date-range filter on ``cepr.org/voxeu/search-all-columns``
    (``date[min]``/``date[max]`` GET params in YYYY-MM-DD format). The search
    sorts newest-first; for the full 2010-present window a single date range
    produces hundreds of pages and reliably times out somewhere past page ~400.
    The prior implementation swallowed that timeout and reported the source
    "completed" with only the 2019-present columns captured (9 years lost).

    Fix: shard the search by year. Each year has ~250-500 columns → ~30-50
    pages, well under the timeout threshold. Recovers the historical archive.
    """

    source_id = "voxeu"

    _SEARCH_URL = "https://cepr.org/voxeu/search-all-columns"
    _BASE = "https://cepr.org"
    _PAGE_TIMEOUT = 60.0

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        for year in range(start.year, end.year + 1):
            year_start = max(start, date(year, 1, 1))
            year_end = min(end, date(year, 12, 31))
            if year_start > year_end:
                continue
            yield from self._fetch_year(year_start, year_end, seen)

    def _fetch_year(
        self, start: date, end: date, seen: set[str]
    ) -> Iterator[Article]:
        page = 0
        while True:
            params = {
                "date[min]": start.isoformat(),
                "date[max]": end.isoformat(),
                "page": page,
            }
            try:
                resp = requests.get(
                    self._SEARCH_URL, params=params, headers=_HEADERS,
                    timeout=self._PAGE_TIMEOUT,
                )
                resp.raise_for_status()
            except Exception as exc:
                log.warning(
                    "VoxEU search shard %s..%s page %d: %s — moving to next shard",
                    start, end, page, exc,
                )
                return

            soup = BeautifulSoup(resp.text, "lxml")
            articles = soup.select("article.c-card")
            if not articles:
                return

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
                body, fetched_title, author, _ = _fetch_page_full(url, min_words=50)
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

    PIIE's individual article pages return HTTP 403 from residential IPs
    (Cloudflare protection). The listing pages are accessible and contain
    title, date, author, and URL. Full article body is attempted but falls
    back to title-only if the page is blocked.

    From university IPs (RCC Midway3) the full body fetch succeeds. The
    listing covers policy-briefs, working-papers, piie-briefings, and
    key research blogs.

    Note: PIIE URLs encode the publication year, enabling reliable date
    filtering without fetching each article.
    """

    source_id = "piie"

    _LISTING_PATHS = [
        ("/publications/policy-briefs", "policy_brief"),
        ("/publications/working-papers", "working_paper"),
        ("/publications/piie-briefings", "piie_briefing"),
        ("/blogs/realtime-economic-issues-watch", "blog_post"),
        ("/blogs/trade-investment-policy-watch", "blog_post"),
    ]

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
                resp = requests.get(
                    base + path,
                    params={"page": page} if page > 0 else {},
                    headers=_HEADERS,
                    timeout=30.0,
                )
                if resp.status_code in (403, 404):
                    log.warning("PIIE %s page %d: HTTP %d — stopping pagination",
                                path, page, resp.status_code)
                    return
                resp.raise_for_status()
            except Exception as exc:
                log.warning("PIIE %s page %d: %s — stopping pagination", path, page, exc)
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
                body, fetched_title, _, _pd = _fetch_page_full(url, min_words=50)
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
    Treasury Secretary testimony is retrieved from the Treasury press release page.

    Note: fed.py's FederalReserveIngestor already ingests Fed Chair testimony
    from federalreserve.gov/testimony. This ingestor fetches Treasury Secretary
    testimony from Treasury.gov, which is not covered elsewhere.

    To avoid duplicating Fed Chair testimony, this ingestor only fetches
    Treasury Secretary testimony. Fed Chair testimony from fed.py's ingestor
    is sufficient for that source.
    """

    source_id = "congressional"

    # Secretary Statements & Remarks listing (Drupal, date-range filterable).
    # Treasury.gov links follow /news/press-releases/sb#### pattern.
    _LISTING_URL = "https://home.treasury.gov/news/press-releases"
    _TREASURY_BASE = "https://home.treasury.gov"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        seen: set[str] = set()
        yield from self._fetch_treasury_testimony(start, end, seen)

    # Maximum number of listing pages to scan when paginating backward to a
    # historical window. Treasury press releases run ~5–10 per day; 2010-2025
    # covers ~50,000 releases at ~20 per listing page, so 2500 pages is the
    # theoretical worst case. We cap at 1200 (≈19,000 releases) to give
    # comfortable headroom for a full 2010-present sweep while still bounding
    # runaway loops on misconfigured calls. Restricting to
    # category=Secretary Statements & Remarks reduces traffic significantly.
    _MAX_LISTING_PAGES = 1200
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
                body, fetched_title, author, page_date = _fetch_page_full(url, min_words=30)
                if not body or len(body.split()) < 20:
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
      - ``GOVINFO_API_KEY`` env var. Falls back to ``DEMO_KEY`` (30 req/hr)
        with a loud warning — fine for integration tests, NOT for the
        full ingest. Free signup at https://api.govinfo.gov/signup/.
    """

    source_id = "cea"

    _GOVINFO_BASE = "https://api.govinfo.gov"
    _COLLECTION = "ERP"
    _PUBLISH_DATE_FMT = "%Y-%m-%d"
    _DEMO_KEY = "DEMO_KEY"

    @classmethod
    def _api_key(cls) -> str:
        key = os.environ.get("GOVINFO_API_KEY")
        if not key:
            log.warning(
                "GOVINFO_API_KEY not set — using DEMO_KEY (30 req/hr). "
                "For the full ingest, sign up at https://api.govinfo.gov/signup/ "
                "(free) and set GOVINFO_API_KEY in .env."
            )
            return cls._DEMO_KEY
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
        """Download a PDF and return its extracted text (best-effort)."""
        try:
            from pypdf import PdfReader
            from io import BytesIO
        except ImportError:
            log.error(
                "pypdf not installed — CEA PDF text extraction disabled. "
                "Install with `pip install pypdf` (see requirements.txt / ADR-020)."
            )
            return ""
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

    # Hard upper bound, refreshed periodically. Calibration on 2026-05-20:
    # w33500 ≈ Feb 2025. NBER publishes ~1500 working papers/year. A
    # ceiling of (latest_floor + 3000) is generous through 2026.
    _ABSOLUTE_CEILING = 38000

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        floor_year = start.year
        ceiling_year = end.year
        floor = self._PAPER_FLOOR_BY_YEAR.get(
            floor_year, min(self._PAPER_FLOOR_BY_YEAR.values()),
        )
        # Ceiling: one year past the requested end, capped at absolute ceiling.
        # If end is in the current year, use the absolute ceiling — we don't
        # know the head without probing.
        ceiling = min(
            self._PAPER_FLOOR_BY_YEAR.get(ceiling_year + 1, self._ABSOLUTE_CEILING),
            self._ABSOLUTE_CEILING,
        )
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
