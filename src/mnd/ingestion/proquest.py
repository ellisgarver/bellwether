"""ProQuest TDM Studio Workbench ingestor — database_native mode (plan §6.1, ADR-004).

Access confirmed: UChicago Global Newsstream via ProQuest TDM Studio Workbench.
Covers WSJ, FT, Reuters, Bloomberg, and most Tier 1/2 whitelist outlets.

Do NOT switch to Factiva — the UChicago license prohibits automated text mining.

This ingestor runs in database_native mode: it queries ProQuest directly using
outlet + date filters rather than looking up GDELT-discovered URLs. This is
more reliable and avoids brittle URL-to-database matching.

Credentials (set in .env):
    PROQUEST_API_TOKEN   — obtain from your TDM Studio project dashboard
    PROQUEST_ACCOUNT_ID  — your institutional account ID
    PROQUEST_PROJECT_ID  — the project ID shown in the workbench

Authentication: Bearer token passed in Authorization header.
Database: Global Newsstream (ProQuest database identifier).

TODO: Validate exact endpoint URLs and response schema against the TDM Studio
      API documentation available inside the workbench environment. The structure
      below follows ProQuest TDM Studio REST API conventions as documented in
      the workbench Jupyter environment.
"""
from __future__ import annotations

import os
import time
from datetime import date
from typing import Any, Iterator

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.config import load_config, load_yaml, project_root
from mnd.utils.logging import get_logger

log = get_logger(__name__)

# ProQuest TDM Studio API base URL (verify against workbench documentation)
_TDMSTUDIO_BASE = "https://tdmstudio.proquest.com/api/v1"
_DATABASE_ID = "global-newsstream"
_PAGE_SIZE = 100
_REQUEST_DELAY_S = 0.5  # be polite; TDM Studio rate limits apply


class PaywalledSourceIngestor(Ingestor):
    """ProQuest TDM Studio Workbench ingestor for paywalled outlet full text.

    Mode ``database_native`` (default and only supported mode): queries
    ProQuest Global Newsstream directly by outlet name + date range.
    """

    source_id = "proquest_tdm"

    def __init__(self, mode: str = "database_native") -> None:
        if mode != "database_native":
            raise ValueError(
                f"Only 'database_native' mode is supported for ProQuest TDM. "
                f"Got: {mode!r}. The url_keyed mode is not implemented."
            )
        self.mode = mode
        self._token: str | None = None
        self._whitelist: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Yield full-text Articles for whitelisted paywalled outlets.

        Raises EnvironmentError if ProQuest credentials are not configured.
        """
        token = self._get_token()
        outlets = self._get_paywalled_outlets()
        log.info(
            "ProQuest TDM: fetching %d paywalled outlets %s → %s",
            len(outlets), start, end,
        )

        for outlet in outlets:
            pub_name = outlet.get("proquest_publication_name") or outlet.get("name", "")
            if not pub_name:
                log.warning("Outlet %s has no proquest_publication_name; skipping", outlet.get("id"))
                continue
            log.info("  Querying: %s", pub_name)
            yield from self._fetch_outlet(token, pub_name, outlet, start, end)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        if self._token:
            return self._token
        token = os.environ.get("PROQUEST_API_TOKEN", "").strip()
        if not token:
            raise EnvironmentError(
                "PROQUEST_API_TOKEN is not set. "
                "Obtain it from your TDM Studio project dashboard at "
                "https://tdmstudio.proquest.com and add it to .env."
            )
        self._token = token
        return token

    def _get_paywalled_outlets(self) -> list[dict[str, Any]]:
        """Return whitelist entries where access == 'paywalled' or 'mixed'."""
        if self._whitelist is not None:
            return self._whitelist
        wl = load_yaml("config/whitelist.yaml")
        outlets = []
        for tier_key, tier_outlets in wl.items():
            if not isinstance(tier_outlets, list):
                continue
            for outlet in tier_outlets:
                if outlet.get("access") in ("paywalled", "mixed"):
                    outlets.append(outlet)
        self._whitelist = outlets
        return outlets

    def _fetch_outlet(
        self,
        token: str,
        pub_name: str,
        outlet: dict[str, Any],
        start: date,
        end: date,
    ) -> Iterator[Article]:
        """Page through ProQuest results for one publication."""
        try:
            import httpx
        except ImportError as exc:
            raise ImportError("httpx is required. `pip install httpx`.") from exc

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        params = {
            "database": _DATABASE_ID,
            "publication": pub_name,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "pageSize": _PAGE_SIZE,
            "fields": "id,title,fullText,publicationDate,authors,url",
        }

        page = 1
        while True:
            params["page"] = page
            time.sleep(_REQUEST_DELAY_S)

            # TODO: Confirm exact endpoint path from TDM Studio API docs
            # (accessible inside the workbench Jupyter environment).
            resp = httpx.get(
                f"{_TDMSTUDIO_BASE}/search",
                params=params,
                headers=headers,
                timeout=60.0,
            )
            if resp.status_code == 401:
                raise EnvironmentError(
                    "ProQuest API returned 401 Unauthorized. "
                    "Check PROQUEST_API_TOKEN in .env."
                )
            resp.raise_for_status()
            data = resp.json()

            records = data.get("documents", data.get("records", []))
            if not records:
                break

            for rec in records:
                article = self._parse_record(rec, outlet)
                if article is not None:
                    yield article

            # Pagination: stop when we've seen all pages
            total = data.get("totalResults", data.get("total", 0))
            if page * _PAGE_SIZE >= total:
                break
            page += 1

    def _parse_record(
        self, rec: dict[str, Any], outlet: dict[str, Any]
    ) -> Article | None:
        """Convert a ProQuest API record to an Article.

        TODO: Adjust field names to match the actual TDM Studio response
        schema (verifiable inside the workbench environment).
        """
        # ProQuest TDM Studio field names (adjust if API differs)
        title = rec.get("title") or rec.get("Title", "")
        body = rec.get("fullText") or rec.get("FullText") or rec.get("abstract", "")
        pub_date = rec.get("publicationDate") or rec.get("PublicationDate", "")
        url = rec.get("url") or rec.get("URL") or rec.get("sourceLink", "")
        doc_id = str(rec.get("id") or rec.get("ProQuestID") or rec.get("documentId", ""))
        author_field = rec.get("authors") or rec.get("Authors")
        author = (
            ", ".join(author_field) if isinstance(author_field, list) else str(author_field or "")
        ) or None

        if not title and not body:
            return None

        # Normalise publication date to ISO 8601
        published_at = _normalise_date(pub_date)

        article_id = _stable_article_id(outlet.get("id", "proquest"), url or doc_id)
        word_count = len(body.split()) if body else 0

        return Article(
            article_id=article_id,
            source_id=outlet.get("id", "proquest"),
            url=url,
            published_at=published_at,
            retrieved_at=_now_utc_iso(),
            title=title,
            body=body,
            author=author,
            language="en",
            tier=outlet.get("tier", 1),
            access=outlet.get("access", "paywalled"),
            retrieval="proquest_tdm_native",
            word_count=word_count,
            raw_metadata={"proquest_doc_id": doc_id},
        )


def _normalise_date(raw: str) -> str:
    """Best-effort conversion of ProQuest date strings to ISO 8601 UTC."""
    if not raw:
        return _now_utc_iso()
    raw = raw.strip()
    # Common ProQuest formats: "2023-03-15", "03/15/2023", "March 15, 2023"
    from datetime import datetime

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            continue
    return _now_utc_iso()
