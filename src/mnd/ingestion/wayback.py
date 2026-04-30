"""Internet Archive Wayback Machine CDX-based article discovery.

ADR-005: replaces GDELT as the historical free-outlet discovery layer.
GDELT's free API applies IP-level rate throttling that makes bulk historical
queries unreliable regardless of per-request delay. See ADR-005 in
docs/architecture_decisions.md for full rationale.

GDELT remains in the codebase (src/mnd/ingestion/gdelt.py) for near-real-time
discovery (last 7 days) where request volume is low enough to avoid throttling.

Discovery pipeline:
  WaybackIngestor.fetch()
    → _cdx_query(pattern, start, end, matchType)   # CDX API call per pattern
    → _looks_like_article(url)                      # path heuristic filter
    → _fetch_archived(url, timestamp)               # Wayback `if_` fetch
    → trafilatura.extract(json)                     # boilerplate removal
    → yield Article

Per-outlet CDX patterns:
  Outlets in config/whitelist.yaml may specify `cdx_url_patterns`, a list of
  URL prefixes (no scheme) used with matchType=prefix. This is critical for
  high-traffic domains where the domain wildcard (matchType=domain) times out
  server-side or returns thousands of parameterized non-article URLs.
  Outlets without `cdx_url_patterns` fall back to domain wildcard.
"""
from __future__ import annotations

import json
import time
from datetime import date
from typing import Iterator
from urllib.parse import urlparse

import requests
import trafilatura

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.config import load_yaml
from mnd.utils.logging import get_logger

log = get_logger(__name__)

CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_FETCH = "https://web.archive.org/web/{timestamp}if_/{url}"

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}

# Path segments that reliably indicate non-article pages (exact segment match).
# Keep narrow — over-filtering here silently drops real articles.
_EXCLUDE_SEGMENTS = frozenset([
    "tag", "tags", "category", "categories", "author", "authors",
    "search", "feed", "rss", "sitemap", "wp-json",
    "cdn-cgi", "static", "img", "images", "assets",
    "about", "contact", "subscribe", "newsletters", "advertise",
    "terms", "privacy", "login", "register", "account",
    "video", "videos", "podcast", "podcasts", "live",
    "watchlist", "quotes", "chart", "charts", "screener",
])

_EXCLUDE_EXTENSIONS = frozenset([".pdf", ".xml", ".json", ".csv", ".zip", ".gz", ".mp4", ".mp3"])


def _looks_like_article(url: str) -> bool:
    """Return True if the URL is plausibly an article (not a tag/index page)."""
    try:
        p = urlparse(url)
        if p.query:
            return False
        path = p.path.rstrip("/")
        parts = [seg for seg in path.split("/") if seg]
        if len(parts) < 2:
            return False
        if any(seg.lower() in _EXCLUDE_SEGMENTS for seg in parts):
            return False
        if any(path.lower().endswith(ext) for ext in _EXCLUDE_EXTENSIONS):
            return False
        slug = parts[-1].lower()
        if not any(c.isalpha() for c in slug):
            return False
        return True
    except Exception:
        return False


def _load_free_outlets() -> list[dict]:
    """Return all free/mixed outlets from the whitelist, excluding Fed-ingestor domains."""
    wl = load_yaml("config/whitelist.yaml")
    outlets = []
    for tier_key in ("tier_1_core_financial_press", "tier_2_adjacent_analytical", "tier_3_institutional"):
        tier_num = int(tier_key.split("_")[1])
        for entry in wl.get(tier_key, []):
            if entry.get("access", "paywalled") not in ("free", "mixed"):
                continue
            if entry.get("retrieval") in ("fed_site",):
                continue
            outlets.append({**entry, "tier": tier_num})
    return outlets


def _cdx_query(url_pattern: str, start: date, end: date, limit: int, match_type: str = "domain") -> list[tuple[str, str]]:
    """Query CDX API; return (original_url, timestamp) pairs deduped by urlkey.

    Args:
        url_pattern: CDX url param — e.g. "*.reuters.com/*" or "www.piie.com/blogs/"
        match_type: "domain" for wildcard expansion, "prefix" for path-prefix queries.
    """
    params = [
        ("url", url_pattern),
        ("matchType", match_type),
        ("output", "json"),
        ("from", start.strftime("%Y%m%d")),
        ("to", end.strftime("%Y%m%d")),
        ("limit", str(limit)),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "urlkey"),
        ("fl", "original,timestamp"),
    ]
    try:
        resp = requests.get(CDX_API, params=params, headers=_HEADERS, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("CDX query failed for %s: %s", url_pattern, exc)
        return []

    try:
        rows = resp.json()
    except Exception:
        return []

    if not rows or len(rows) < 2:
        return []

    return [(row[0], row[1]) for row in rows[1:] if len(row) >= 2]


def _fetch_archived(url: str, timestamp: str) -> str | None:
    """Fetch archived HTML from Wayback. `if_` modifier strips the toolbar."""
    wb_url = WAYBACK_FETCH.format(timestamp=timestamp, url=url)
    try:
        resp = requests.get(wb_url, headers=_HEADERS, timeout=25)
        if resp.status_code == 200 and resp.text:
            return resp.text
    except Exception as exc:
        log.debug("Wayback fetch failed for %s: %s", url, exc)
    return None


def _extract(html: str, url: str) -> tuple[str, str, str]:
    """Run trafilatura; return (text, title, pub_date_iso)."""
    try:
        raw = trafilatura.extract(
            html,
            url=url,
            output_format="json",
            include_comments=False,
            include_tables=False,
            favor_recall=True,
            no_fallback=False,
        )
        if raw:
            data = json.loads(raw)
            return (
                data.get("text") or "",
                data.get("title") or "",
                data.get("date") or "",
            )
    except Exception as exc:
        log.debug("trafilatura extract failed for %s: %s", url, exc)
    return "", "", ""


class WaybackIngestor(Ingestor):
    """Fetches article text for free outlets via Wayback Machine CDX + archived HTML.

    For each outlet in config/whitelist.yaml (free/mixed, non-Fed), queries CDX
    for article URLs captured in the requested date window using either:

    - Per-outlet ``cdx_url_patterns`` (matchType=prefix) — preferred, required
      for high-traffic domains where the domain wildcard times out.
    - Domain wildcard fallback (matchType=domain) for outlets without patterns.

    See module docstring and ADR-005 for design rationale.
    """

    source_id = "wayback"

    def __init__(
        self,
        max_per_pattern: int = 200,
        cdx_pause: float = 1.0,
        fetch_pause: float = 1.5,
        min_words: int = 200,
    ) -> None:
        self.max_per_pattern = max_per_pattern
        self.cdx_pause = cdx_pause
        self.fetch_pause = fetch_pause
        self.min_words = min_words
        self._outlets = _load_free_outlets()

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        log.info(
            "WaybackIngestor: %d free outlets, window %s → %s",
            len(self._outlets), start, end,
        )

        for outlet in self._outlets:
            outlet_name = outlet.get("name", outlet.get("id", "?"))
            cdx_patterns = outlet.get("cdx_url_patterns", [])
            section_filter = [s.lower() for s in outlet.get("section_filter", [])]

            if cdx_patterns:
                # Use per-outlet path-prefix queries (more targeted, avoids timeouts)
                candidates: list[tuple[str, str]] = []
                seen: set[str] = set()
                per_pattern_limit = min(self.max_per_pattern, 250)

                for pattern in cdx_patterns:
                    log.info("CDX prefix query: %s (%s)", pattern, outlet_name)
                    rows = _cdx_query(pattern, start, end, per_pattern_limit, match_type="prefix")
                    time.sleep(self.cdx_pause)
                    for url, ts in rows:
                        if url not in seen:
                            candidates.append((url, ts))
                            seen.add(url)
            else:
                # Fallback: domain wildcard per domain entry
                candidates = []
                for domain in outlet.get("domains", []):
                    bare = domain.split("/")[0]  # strip any path from domain entries
                    log.info("CDX domain query: %s (%s)", bare, outlet_name)
                    cdx_limit = min(self.max_per_pattern * 5, 500)
                    rows = _cdx_query(f"*.{bare}/*", start, end, cdx_limit, match_type="domain")
                    time.sleep(self.cdx_pause)
                    candidates.extend(rows)

            # Filter to article-like URLs
            filtered = [
                (url, ts) for url, ts in candidates
                if _looks_like_article(url)
            ]

            if section_filter:
                filtered = [
                    (url, ts) for url, ts in filtered
                    if any(sf in url.lower() for sf in section_filter)
                ]

            # Cap and fetch
            filtered = filtered[: self.max_per_pattern]
            total_candidates = len(candidates)
            log.info(
                "  %s: %d CDX hits → %d article-like → fetching",
                outlet_name, total_candidates, len(filtered),
            )

            n_ok = 0
            for url, timestamp in filtered:
                html = _fetch_archived(url, timestamp)
                time.sleep(self.fetch_pause)

                if not html:
                    continue

                text, title, pub_date = _extract(html, url)
                if not text or len(text.split()) < self.min_words:
                    continue

                # Resolve published_at: trafilatura date preferred, fall back to CDX timestamp
                if pub_date:
                    published_at = pub_date if "T" in pub_date else pub_date + "T00:00:00Z"
                else:
                    ts = timestamp
                    published_at = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}Z"

                # Gate on date range (CDX from/to is approximate — trafilatura date is better)
                try:
                    from datetime import datetime
                    art_date = datetime.fromisoformat(published_at.rstrip("Z")).date()
                    if art_date < start or art_date > end:
                        continue
                except Exception:
                    pass

                yield Article(
                    article_id=_stable_article_id(outlet["id"], url),
                    source_id=outlet["id"],
                    url=url,
                    published_at=published_at,
                    retrieved_at=_now_utc_iso(),
                    title=title or url.rsplit("/", 1)[-1],
                    body=text,
                    author=None,
                    section=outlet.get("id"),
                    language="en",
                    tier=outlet["tier"],
                    access=outlet.get("access", "free"),
                    retrieval="wayback",
                    word_count=len(text.split()),
                    raw_metadata={
                        "wayback_timestamp": timestamp,
                        "cdx_pattern": url.split("/")[2] if "/" in url else url,
                        "outlet_id": outlet["id"],
                    },
                )
                n_ok += 1

            log.info("  %s: %d articles yielded", outlet_name, n_ok)
