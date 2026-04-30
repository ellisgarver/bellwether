"""GDELT 2.0 ingestion.

GDELT is the *discovery* layer — we use it to surface URLs published by
outlets on our whitelist, NOT as a primary text source. Full text retrieval
is handled by other ingestors (factiva, fed_site, etc.) keyed off URLs
discovered here.

GDELT has documented quality issues (~55% accuracy, ~20% redundancy,
Western/U.S. media overrepresentation). We mitigate by:
  - Filtering aggressively to whitelisted source domains.
  - Running MinHash dedup downstream.
  - Cross-checking against alternate news APIs (compress-able).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterator
from urllib.parse import urlparse

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.config import load_yaml
from mnd.utils.logging import get_logger

log = get_logger(__name__)


def _normalize_domain(url: str) -> str:
    """Extract a www-stripped lowercase domain from a URL."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host.removeprefix("www.")


def _build_whitelist_index() -> dict[str, dict]:
    """Map each whitelisted domain to its outlet metadata."""
    wl = load_yaml("config/whitelist.yaml")
    index: dict[str, dict] = {}
    for tier_key in ("tier_1_core_financial_press", "tier_2_adjacent_analytical", "tier_3_institutional"):
        tier_num = int(tier_key.split("_")[1])
        for entry in wl.get(tier_key, []):
            for domain in entry.get("domains", []):
                index[domain.lower().removeprefix("www.")] = {**entry, "tier": tier_num}
    return index


class GdeltIngestor(Ingestor):
    """Discovery-layer ingestor over GDELT 2.0 article search."""

    source_id = "gdelt"

    def __init__(self, max_per_query: int = 250, request_pause_seconds: float = 6.0, batch_days: int = 7) -> None:
        self.max_per_query = max_per_query
        self.request_pause_seconds = request_pause_seconds  # GDELT rate-limits to 1 req/5s
        self.batch_days = batch_days  # query in weekly chunks to stay within rate limit
        self._whitelist = _build_whitelist_index()
        self._whitelist_domains = sorted(self._whitelist.keys())

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Yield URL-and-headline records for whitelisted outlets in [start, end].

        We query GDELT day-by-day (rather than all at once) because the
        ArticleList endpoint caps results per query. Per-day queries
        per-outlet would be cleaner but slower; we aggregate by day and
        filter by domain in post.
        """
        try:
            from gdeltdoc import GdeltDoc, Filters
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "gdeltdoc is required. Install via `pip install gdeltdoc`."
            ) from exc

        import time

        gd = GdeltDoc()
        # Broad keyword scopes GDELT to economic coverage; domain filter keeps only whitelist.
        _KEYWORD = "economy OR inflation OR recession OR markets OR Fed OR monetary"

        current = start
        batch_num = 0
        while current <= end:
            batch_end = min(current + timedelta(days=self.batch_days - 1), end)
            window_label = f"{current} → {batch_end}"

            # Honour GDELT rate limit: sleep before every request except the first
            if batch_num > 0:
                time.sleep(self.request_pause_seconds)
            batch_num += 1

            try:
                articles_df = gd.article_search(
                    filters=Filters(
                        start_date=current.isoformat(),
                        end_date=batch_end.isoformat(),
                        keyword=_KEYWORD,
                        country="US",
                        language="english",
                    )
                )
            except Exception as exc:
                log.warning("GDELT query failed for %s: %s", window_label, exc)
                current = batch_end + timedelta(days=1)
                continue

            if articles_df is None or len(articles_df) == 0:
                log.debug("GDELT returned 0 articles for %s", window_label)
                current = batch_end + timedelta(days=1)
                continue

            n_yielded = 0
            for _, row in articles_df.iterrows():
                url = str(row.get("url", "")).strip()
                if not url:
                    continue
                domain = _normalize_domain(url)
                outlet = self._whitelist.get(domain)
                if outlet is None:
                    continue  # not on whitelist

                title = str(row.get("title", "")).strip()
                seen_at = row.get("seendate") or current.isoformat()
                yield Article(
                    article_id=_stable_article_id(outlet["id"], url),
                    source_id=outlet["id"],
                    url=url,
                    published_at=str(seen_at),
                    retrieved_at=_now_utc_iso(),
                    title=title,
                    body="",  # GDELT is metadata only; body fetched downstream
                    section=row.get("sourcecountry") or None,
                    language="en",
                    tier=outlet["tier"],
                    access=outlet.get("access", "free"),
                    retrieval=outlet.get("retrieval", "gdelt_url"),
                    word_count=0,
                    raw_metadata={"gdelt_domain": domain, "gdelt_seendate": str(seen_at)},
                )
                n_yielded += 1

            log.info("GDELT %s: %d whitelisted articles", window_label, n_yielded)
            current = batch_end + timedelta(days=1)
