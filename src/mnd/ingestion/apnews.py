"""Tier 4 open journalism ingestors: AP News and MarketWatch.

Both sources share the same Wayback CDX + RSS retrieval pattern and produce
identical Article schema records. They are in the same module because the
ingestion logic is structurally identical; they differ only in URL patterns,
RSS feeds, and metadata.

AP News (APNewsIngestor)
  Wire journalism: event detection, factual coverage. Fully open.
  Historical (2010–present): Wayback CDX on apnews.com patterns.
  Phase 6 live: AP business RSS feed.

  URL patterns in Wayback:
    apnews.com/article/...    — standard AP story format (2019–present)
    apnews.com/business/...   — section index; article links within
    apnews.com/economy/...    — section index
    Pre-2019 AP URLs are often apnews.com/[32-char hex slug]; caught by
    the /article/ prefix fallback when that pattern has sparse results.

MarketWatch (MarketWatchIngestor)
  Analytical financial journalism: interpretive and framing pieces at the
  wire-to-analysis intersection AP misses. 15-20 macro analytical pieces/day.
  Fully open, Dow Jones property. Reinstated in ADR-009.

  Historical (2010–present): Wayback CDX on www.marketwatch.com/story/.
  Phase 6 live: MarketWatch top-stories RSS feed.

  Coverage note: Pre-2015 Wayback CDX coverage is thinner than post-2015.
  Treat corpus as consistent from 2015-01-01 onward. Pre-2015 articles are
  ingested when available but flagged in corpus composition QA output.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urlparse

import feedparser
import requests
import trafilatura
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}

CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_FETCH = "https://web.archive.org/web/{timestamp}if_/{url}"

_AP_CDX_PATTERNS = [
    "apnews.com/article/",
    "apnews.com/business/",
    "apnews.com/economy/",
]
_AP_LIVE_RSS = "https://feeds.apnews.com/rss/business"

_MW_CDX_PATTERNS = [
    "www.marketwatch.com/story/",
]
_MW_LIVE_RSS = "https://feeds.marketwatch.com/marketwatch/topstories/"
# Pre-2015 Wayback CDX coverage is thinner. Articles before this date are
# ingested when available but flagged in corpus composition QA.
_MW_CONSISTENT_START = "2015-01-01"

_MIN_BODY_WORDS = 100


@retry(
    retry=retry_if_exception_type((
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    )),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _cdx_get(params: dict) -> requests.Response:
    return requests.get(CDX_API, params=params, headers=_HEADERS, timeout=60.0)


@retry(
    retry=retry_if_exception_type((
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    )),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _wayback_get(url: str) -> requests.Response:
    return requests.get(url, headers=_HEADERS, timeout=45.0, allow_redirects=True)


def _is_article_url(url: str, *, domain: str = "apnews") -> bool:
    """Heuristic: exclude index pages, search, multimedia, and tag pages.

    domain: 'apnews' or 'marketwatch' to apply site-specific rules.
    """
    path = urlparse(url).path.rstrip("/")
    exclude_segments = {
        "index", "search", "video", "photo", "audio", "gallery",
        "tag", "topic", "hub", "wire", "sports", "entertainment",
    }
    parts = set(path.lower().split("/"))
    if parts & exclude_segments:
        return False

    if domain == "apnews":
        # AP article slugs are either /article/<slug> or legacy 32-char hex
        if "/article/" in path:
            return True
        segments = [s for s in path.split("/") if s]
        if segments and len(segments[-1]) >= 20:
            return True
        return False

    if domain == "marketwatch":
        # MarketWatch article URLs are always /story/<slug>
        return "/story/" in path

    return False


def _cdx_query(pattern: str, start: date, end: date, *, domain: str = "apnews") -> list[tuple[str, str]]:
    """Return deduplicated (url, timestamp) pairs from Wayback CDX for a URL prefix."""
    params = {
        "url": pattern,
        "matchType": "prefix",
        "output": "json",
        "fl": "original,timestamp,statuscode",
        "filter": "statuscode:200",
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "collapse": "urlkey",
        "limit": 50000,
    }
    try:
        resp = _cdx_get(params)
        resp.raise_for_status()
        rows = resp.json()
        if not rows or len(rows) < 2:
            return []
        # First row is header ["original","timestamp","statuscode"]
        pairs = []
        for row in rows[1:]:
            url, ts, sc = row[0], row[1], row[2]
            if sc == "200" and _is_article_url(url, domain=domain):
                pairs.append((url, ts))
        # Deduplicate by URL, keeping first (earliest) timestamp
        seen: set[str] = set()
        result = []
        for url, ts in pairs:
            if url not in seen:
                seen.add(url)
                result.append((url, ts))
        return result
    except Exception as exc:
        log.warning("CDX query failed for %s: %s", pattern, exc)
        return []


def _fetch_archived(url: str, timestamp: str) -> str | None:
    """Fetch a Wayback archived page and extract article text."""
    archived_url = WAYBACK_FETCH.format(timestamp=timestamp, url=url)
    try:
        resp = _wayback_get(archived_url)
        text = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        return text
    except Exception as exc:
        log.debug("Wayback fetch failed for %s: %s", url, exc)
        return None


class APNewsIngestor(Ingestor):
    """AP News ingestor.

    Historical (2010–present): Wayback CDX API, scoped to AP News URL patterns.
    Phase 6 live: fetch_live_rss() using AP's business RSS feed.

    The fetch() method covers historical ingestion. Call fetch_live_rss() for
    the Phase 6 weekly update cron.
    """

    source_id = "apnews"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Historical ingestion via Wayback CDX for apnews.com URL patterns."""
        seen: set[str] = set()
        for pattern in _AP_CDX_PATTERNS:
            log.info("AP News CDX query: %s [%s → %s]", pattern, start, end)
            results = _cdx_query(pattern, start, end, domain="apnews")
            log.info("AP News CDX found %d URLs for pattern %s", len(results), pattern)
            for url, timestamp in results:
                if url in seen:
                    continue
                seen.add(url)
                body = _fetch_archived(url, timestamp)
                if not body or len(body.split()) < _MIN_BODY_WORDS:
                    continue
                # Approximate pub_date from Wayback timestamp (YYYYMMDD...)
                try:
                    pub_date = datetime.strptime(timestamp[:8], "%Y%m%d").date()
                except Exception:
                    pub_date = start
                yield Article(
                    article_id=_stable_article_id(self.source_id, url),
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    retrieved_at=_now_utc_iso(),
                    title=_extract_ap_title(body),
                    body=body,
                    author=None,
                    section="business",
                    language="en",
                    tier=4,
                    access="free",
                    retrieval="wayback_cdx",
                    word_count=len(body.split()),
                    raw_metadata={
                        "document_type": "ap_news_article",
                        "wayback_timestamp": timestamp,
                        "cdx_pattern": pattern,
                    },
                )
                time.sleep(0.5)

    def fetch_live_rss(self, start: date, end: date) -> Iterator[Article]:
        """Phase 6: fetch recent AP News articles via business RSS feed."""
        try:
            feed = feedparser.parse(_AP_LIVE_RSS, request_headers={"User-Agent": USER_AGENT})
        except Exception as exc:
            log.error("AP News RSS fetch failed: %s", exc)
            return
        for entry in feed.entries:
            pub_date = None
            for attr in ("published_parsed", "updated_parsed"):
                val = getattr(entry, attr, None)
                if val:
                    try:
                        pub_date = date(*val[:3])
                    except Exception:
                        pass
                    break
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            title = entry.get("title", "AP News article")
            # RSS summary is a snippet; fetch full body
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=30.0)
                body = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
            except Exception:
                body = None
            if not body:
                body = entry.get("summary", "")
            if not body or len(body.split()) < 30:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, url),
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=title,
                body=body,
                author=entry.get("author"),
                section="business",
                language="en",
                tier=4,
                access="free",
                retrieval="rss",
                word_count=len(body.split()),
                raw_metadata={"document_type": "ap_news_article"},
            )
            time.sleep(0.3)


class MarketWatchIngestor(Ingestor):
    """MarketWatch ingestor (Tier 4 — analytical financial journalism).

    MarketWatch fills the interpretive/framing gap AP News does not cover:
    analytical macro commentary, market narratives, and economic analysis.
    Fully open, Dow Jones property. Reinstated in ADR-009.

    Historical (2010–present): Wayback CDX on www.marketwatch.com/story/.
    Phase 6 live: fetch_live_rss() using MarketWatch top-stories RSS.

    Coverage note: pre-2015 Wayback CDX coverage is thinner. The ingestor
    fetches whatever is available but tags pre-2015 records with
    raw_metadata["sparse_wayback_coverage"] = True for QA flagging.
    Treat corpus as consistent from 2015-01-01 onward for cross-year analysis.
    """

    source_id = "marketwatch"

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Historical ingestion via Wayback CDX for marketwatch.com/story/."""
        seen: set[str] = set()
        for pattern in _MW_CDX_PATTERNS:
            log.info("MarketWatch CDX query: %s [%s → %s]", pattern, start, end)
            results = _cdx_query(pattern, start, end, domain="marketwatch")
            log.info("MarketWatch CDX found %d URLs for pattern %s", len(results), pattern)
            for url, timestamp in results:
                if url in seen:
                    continue
                seen.add(url)
                body = _fetch_archived(url, timestamp)
                if not body or len(body.split()) < _MIN_BODY_WORDS:
                    continue
                try:
                    pub_date = datetime.strptime(timestamp[:8], "%Y%m%d").date()
                except Exception:
                    pub_date = start
                sparse = pub_date.isoformat() < _MW_CONSISTENT_START
                yield Article(
                    article_id=_stable_article_id(self.source_id, url),
                    source_id=self.source_id,
                    url=url,
                    published_at=pub_date.isoformat() + "T00:00:00Z",
                    retrieved_at=_now_utc_iso(),
                    title=_extract_title(body, fallback="MarketWatch article"),
                    body=body,
                    author=None,
                    section="markets",
                    language="en",
                    tier=4,
                    access="free",
                    retrieval="wayback_cdx",
                    word_count=len(body.split()),
                    raw_metadata={
                        "document_type": "marketwatch_article",
                        "wayback_timestamp": timestamp,
                        "cdx_pattern": pattern,
                        "sparse_wayback_coverage": sparse,
                    },
                )
                time.sleep(0.5)

    def fetch_live_rss(self, start: date, end: date) -> Iterator[Article]:
        """Phase 6: fetch recent MarketWatch articles via top-stories RSS."""
        try:
            feed = feedparser.parse(_MW_LIVE_RSS, request_headers={"User-Agent": USER_AGENT})
        except Exception as exc:
            log.error("MarketWatch RSS fetch failed: %s", exc)
            return
        for entry in feed.entries:
            pub_date = None
            for attr in ("published_parsed", "updated_parsed"):
                val = getattr(entry, attr, None)
                if val:
                    try:
                        pub_date = date(*val[:3])
                    except Exception:
                        pass
                    break
            if not pub_date or pub_date < start or pub_date > end:
                continue
            url = entry.get("link", "")
            if not url or "/story/" not in url:
                continue
            title = entry.get("title", "MarketWatch article")
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=30.0)
                body = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
            except Exception:
                body = None
            if not body:
                body = entry.get("summary", "")
            if not body or len(body.split()) < 30:
                continue
            yield Article(
                article_id=_stable_article_id(self.source_id, url),
                source_id=self.source_id,
                url=url,
                published_at=pub_date.isoformat() + "T00:00:00Z",
                retrieved_at=_now_utc_iso(),
                title=title,
                body=body,
                author=entry.get("author"),
                section="markets",
                language="en",
                tier=4,
                access="free",
                retrieval="rss",
                word_count=len(body.split()),
                raw_metadata={"document_type": "marketwatch_article"},
            )
            time.sleep(0.3)


def _extract_title(body: str, *, fallback: str = "article") -> str:
    """Heuristic: use first non-empty line of body as title."""
    first_line = body.split("\n")[0].strip()
    if len(first_line) > 10:
        return first_line[:120]
    return fallback


def _extract_ap_title(body: str) -> str:
    """Backwards-compatible alias used inside APNewsIngestor."""
    return _extract_title(body, fallback="AP News article")
