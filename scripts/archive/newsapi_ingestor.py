"""NewsAPI ingestor for Phase 6 live/recent wire coverage (Tier 2).

ADR-005 designates GDELT for near-real-time discovery (last 7 days). NewsAPI
complements GDELT by providing structured access to recent articles from Reuters
and Bloomberg — the two Tier 2 outlets not in ProQuest Global Newsstream.

NewsAPI free tier: 100 requests/day; max lookback ~1 month for free accounts.
Paid plans extend lookback and rate limits. Authentication via NEWS_API_KEY env var.

Phase 6 usage:
  python scripts/run_pipeline.py ingest --start <1w-ago> --end <today> --sources newsapi
  (cron weekly; NewsAPI handles what Wayback can't — content <48h old not yet archived)

Wayback CDX remains the primary source for historical bulk (2010-present).
NewsAPI is NOT used for Phase 2/3 full-corpus historical ingestion.
"""
from __future__ import annotations

import os
import time
from datetime import date
from typing import Iterator

import requests

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.config import load_yaml
from mnd.utils.logging import get_logger

log = get_logger(__name__)

NEWSAPI_EVERYTHING = "https://newsapi.org/v2/everything"
_HEADERS = {"User-Agent": "MacroNarrativeDynamics/0.1 (academic research)"}

# Tier 2 wire domains targeted for live coverage
_TIER2_DOMAINS = ["reuters.com", "bloomberg.com"]


def _get_api_key() -> str:
    key = os.environ.get("NEWS_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "NEWS_API_KEY not set. Add it to .env (sign up free at newsapi.org). "
            "NewsAPI is only needed for Phase 6 live updates — historical ingestion "
            "uses Wayback CDX (--sources wayback)."
        )
    return key


class NewsAPIIngestor(Ingestor):
    """Fetches recent wire articles from Reuters/Bloomberg via NewsAPI.

    Targets only the Tier 2 wire outlets (reuters.com, bloomberg.com) that are
    absent from ProQuest Global Newsstream. Results are filtered through the
    whitelist keyword requirements and are subject to the normal topic filter.

    Free-tier constraints:
      - 100 requests/day
      - Results capped at 100 articles per request (pageSize=100)
      - Lookback limited to ~30 days on free plan

    Phase 6 weekly cron: request 7-day window, keep within ~10 req/run budget.
    """

    source_id = "newsapi"

    def __init__(
        self,
        domains: list[str] | None = None,
        page_size: int = 100,
        inter_request_delay: float = 1.0,
    ) -> None:
        self._api_key = _get_api_key()
        self._domains = domains or _TIER2_DOMAINS
        self._page_size = min(page_size, 100)  # NewsAPI cap
        self._delay = inter_request_delay
        self._whitelist = load_yaml("config/whitelist.yaml")

    def _outlet_for_domain(self, url: str) -> dict | None:
        """Find the whitelist outlet entry for a given URL."""
        for tier_key in ("tier_1_core_financial_press", "tier_2_adjacent_analytical"):
            for entry in self._whitelist.get(tier_key, []):
                for d in entry.get("domains", []):
                    if d in url:
                        return entry
        return None

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        log.info(
            "NewsAPIIngestor: fetching %s window %s → %s",
            self._domains, start, end,
        )

        for domain in self._domains:
            yield from self._fetch_domain(domain, start, end)

    def _fetch_domain(self, domain: str, start: date, end: date) -> Iterator[Article]:
        params = {
            "domains": domain,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": self._page_size,
            "apiKey": self._api_key,
        }

        try:
            resp = requests.get(
                NEWSAPI_EVERYTHING, params=params, headers=_HEADERS, timeout=30
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            if resp.status_code == 426:
                log.warning(
                    "NewsAPI 426: free-tier lookback exceeded for %s "
                    "(free plan limit: ~30 days). Upgrade plan or use Wayback for older dates.",
                    domain,
                )
            elif resp.status_code == 429:
                log.warning("NewsAPI 429: rate limit hit for %s.", domain)
            else:
                log.error("NewsAPI request failed for %s: %s", domain, exc)
            return
        except Exception as exc:
            log.error("NewsAPI request error for %s: %s", domain, exc)
            return

        time.sleep(self._delay)

        data = resp.json()
        if data.get("status") != "ok":
            log.warning("NewsAPI non-ok response for %s: %s", domain, data.get("message", ""))
            return

        articles = data.get("articles", [])
        log.info("  %s: %d articles from NewsAPI", domain, len(articles))
        outlet = self._outlet_for_domain(domain) or {}

        n_ok = 0
        for item in articles:
            url = item.get("url", "")
            if not url:
                continue

            body = item.get("content") or item.get("description") or ""
            # NewsAPI truncates content at 200 chars on free plan; body may be short
            word_count = len(body.split())
            if word_count < 30:
                log.debug("NewsAPI: skipping short body (%d words) for %s", word_count, url)
                continue

            published_raw = item.get("publishedAt", "")
            published_at = published_raw if published_raw else _now_utc_iso()

            source_name = item.get("source", {}).get("name", domain)
            source_id = outlet.get("id") or domain.split(".")[0]

            yield Article(
                article_id=_stable_article_id(source_id, url),
                source_id=source_id,
                url=url,
                published_at=published_at,
                retrieved_at=_now_utc_iso(),
                title=item.get("title") or "",
                body=body,
                author=item.get("author"),
                section=None,
                language="en",
                tier=outlet.get("tier", 1),
                access=outlet.get("access", "mixed"),
                retrieval="newsapi",
                word_count=word_count,
                raw_metadata={
                    "newsapi_source": source_name,
                    "newsapi_domain": domain,
                    "description": item.get("description", ""),
                    "truncated": "[+" in (item.get("content") or ""),
                },
            )
            n_ok += 1

        log.info("  %s: %d articles yielded (after word-count filter)", domain, n_ok)
