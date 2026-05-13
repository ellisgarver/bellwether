"""Tier 2 academic ingestor: arXiv preprints (econ.GN, econ.EM, q-fin.EC, q-fin.GN, q-fin.RM).

Uses the arXiv Atom API (export.arxiv.org/api/query) for full historical coverage.
The API returns Atom XML with one entry per paper; we parse it with
xml.etree.ElementTree to avoid adding new dependencies.

Only the abstract (summary field) is used as the document body — full text
is PDF-only and not fetched. Abstracts are sufficient semantic signal for
BERTopic clustering.

Checkpoint/resume: tracks already-fetched arXiv short IDs (e.g. "2301.12345")
in a plain-text checkpoint file, one ID per line. Same pattern as APNewsIngestor.

Excluded categories: econ.TH (theory), econ.ST (statistics/econometrics),
q-fin.CP (computational finance), q-fin.TR (trading/market microstructure).
These are post-fetch filtered by primary_category to avoid irrelevant submissions
that may match the search query via secondary categories.

Rate limit: arXiv asks that bulk exporters sleep >= 3 seconds between requests.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import requests

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}

_ARXIV_API = "http://export.arxiv.org/api/query"

# Categories to include in the search query
_SEARCH_QUERY = (
    "cat:econ.GN OR cat:econ.EM OR cat:q-fin.EC OR cat:q-fin.GN OR cat:q-fin.RM"
)

# Categories to exclude after fetching (post-filter by primary_category)
_EXCLUDED_CATEGORIES: frozenset[str] = frozenset({
    "econ.TH",
    "econ.ST",
    "q-fin.CP",
    "q-fin.TR",
})

_BATCH_SIZE = 100
_RATE_LIMIT_SLEEP = 3.0  # arXiv API guideline: >= 3 seconds between requests

# Atom XML namespaces used by the arXiv API
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def _load_id_checkpoint(checkpoint_path: Path | None) -> set[str]:
    if checkpoint_path and checkpoint_path.exists():
        try:
            ids = set(checkpoint_path.read_text(encoding="utf-8").splitlines())
            log.info(
                "arXiv: loaded checkpoint %s: %d already-fetched IDs",
                checkpoint_path,
                len(ids),
            )
            return ids
        except Exception as exc:
            log.warning(
                "arXiv: could not read checkpoint %s: %s — starting fresh",
                checkpoint_path,
                exc,
            )
    return set()


def _save_id_checkpoint(fetched_ids: set[str], checkpoint_path: Path | None) -> None:
    if checkpoint_path:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text("\n".join(sorted(fetched_ids)), encoding="utf-8")


def _parse_arxiv_id(entry_id_text: str) -> str:
    """Extract short arXiv ID (e.g. '2301.12345') from the full Atom id URL.

    arXiv Atom id is e.g. 'http://arxiv.org/abs/2301.12345v1'.
    We strip the version suffix to get a stable identifier.
    """
    # Last path segment, strip vN version suffix
    short = entry_id_text.strip().rstrip("/").split("/")[-1]
    if "v" in short and short.rsplit("v", 1)[-1].isdigit():
        short = short.rsplit("v", 1)[0]
    return short


def _clean_whitespace(text: str) -> str:
    """Collapse internal whitespace and strip leading/trailing whitespace."""
    return " ".join(text.split())


def _build_date_range(start: date, end: date) -> str:
    """Return arXiv submittedDate range string for the API query."""
    return (
        f"[{start.strftime('%Y%m%d')}0000 TO {end.strftime('%Y%m%d')}2359]"
    )


class ArxivIngestor(Ingestor):
    """arXiv preprint ingestor for Tier 2 academic semantic corpus.

    Fetches papers from the arXiv Atom API in batches of 100, filtered to
    macro-economics and quantitative finance categories:
      econ.GN  General Economics
      econ.EM  Econometrics
      q-fin.EC Economics of Financial Markets
      q-fin.GN General Quantitative Finance
      q-fin.RM Risk Management

    Post-fetch exclusion removes papers whose primary_category is in
    {econ.TH, econ.ST, q-fin.CP, q-fin.TR}.

    Only abstracts are stored as the body — full text is PDF-only.
    Documents are keyed by short arXiv ID (e.g. '2301.12345') for checkpoint.
    """

    source_id = "arxiv"

    def __init__(
        self,
        checkpoint_path: Path | None = None,
        max_results: int | None = None,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._max_results = max_results  # debug: cap total results for testing

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Yield Article records for arXiv papers submitted within [start, end]."""
        fetched_ids = _load_id_checkpoint(self._checkpoint_path)

        date_range = _build_date_range(start, end)
        full_query = f"({_SEARCH_QUERY}) AND submittedDate:{date_range}"

        start_offset = 0
        total_results: int | None = None
        yielded = 0

        try:
            while True:
                if self._max_results is not None and start_offset >= self._max_results:
                    log.info(
                        "arXiv: reached max_results cap (%d); stopping",
                        self._max_results,
                    )
                    break

                batch_size = _BATCH_SIZE
                if self._max_results is not None:
                    batch_size = min(batch_size, self._max_results - start_offset)

                params = {
                    "search_query": full_query,
                    "start": start_offset,
                    "max_results": batch_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                log.info(
                    "arXiv: fetching batch start=%d size=%d [%s → %s]",
                    start_offset,
                    batch_size,
                    start,
                    end,
                )

                resp = None
                for _attempt in range(4):
                    try:
                        resp = requests.get(
                            _ARXIV_API,
                            params=params,
                            headers=_HEADERS,
                            timeout=60.0,
                        )
                        if resp.status_code == 429:
                            wait = 10 * (2 ** _attempt)
                            log.warning("arXiv 429 rate limit; sleeping %ds", wait)
                            time.sleep(wait)
                            resp = None
                            continue
                        resp.raise_for_status()
                        break
                    except requests.exceptions.Timeout:
                        log.warning("arXiv timeout at offset %d (attempt %d/4)", start_offset, _attempt + 1)
                        time.sleep(5 * (2 ** _attempt))
                    except Exception as exc:
                        log.warning("arXiv API request failed at offset %d: %s", start_offset, exc)
                        break
                if resp is None or not resp.ok:
                    log.warning("arXiv: giving up at offset %d after retries", start_offset)
                    break

                try:
                    root = ET.fromstring(resp.content)
                except ET.ParseError as exc:
                    log.warning("arXiv: XML parse error at offset %d: %s", start_offset, exc)
                    break

                # Read totalResults on the first page
                if total_results is None:
                    total_el = root.find("opensearch:totalResults", _NS)
                    if total_el is not None and total_el.text:
                        try:
                            total_results = int(total_el.text)
                            log.info("arXiv: %d total results for query", total_results)
                        except ValueError:
                            total_results = 0
                    else:
                        total_results = 0

                entries = root.findall("atom:entry", _NS)
                if not entries:
                    log.info("arXiv: no entries in batch at offset %d; stopping", start_offset)
                    break

                for entry in entries:
                    article = self._parse_entry(entry, fetched_ids)
                    if article is not None:
                        fetched_ids.add(article.raw_metadata["arxiv_id"])
                        yielded += 1
                        yield article

                start_offset += len(entries)

                # Stop if we've consumed all available results
                if total_results is not None and start_offset >= total_results:
                    log.info(
                        "arXiv: exhausted all %d results; stopping", total_results
                    )
                    break

                # Also stop if the batch returned fewer than requested (last page)
                if len(entries) < batch_size:
                    log.info(
                        "arXiv: partial batch (%d < %d); stopping",
                        len(entries),
                        batch_size,
                    )
                    break

                time.sleep(_RATE_LIMIT_SLEEP)

        finally:
            _save_id_checkpoint(fetched_ids, self._checkpoint_path)
            log.info(
                "arXiv: checkpoint saved (%d total IDs, %d yielded this run)",
                len(fetched_ids),
                yielded,
            )

    def _parse_entry(
        self,
        entry: ET.Element,
        fetched_ids: set[str],
    ) -> Article | None:
        """Parse one Atom <entry> element. Returns None if it should be skipped."""

        # --- ID ---
        id_el = entry.find("atom:id", _NS)
        if id_el is None or not id_el.text:
            return None
        full_url = id_el.text.strip()
        arxiv_id = _parse_arxiv_id(full_url)

        # Normalise the canonical URL (strip version suffix for stable dedup)
        canonical_url = f"https://arxiv.org/abs/{arxiv_id}"

        if arxiv_id in fetched_ids:
            return None

        # --- Primary category (used for exclusion filter) ---
        primary_cat_el = entry.find("arxiv:primary_category", _NS)
        primary_category = ""
        if primary_cat_el is not None:
            primary_category = primary_cat_el.get("term", "").strip()

        if primary_category in _EXCLUDED_CATEGORIES:
            return None

        # --- Title ---
        title_el = entry.find("atom:title", _NS)
        title = _clean_whitespace(title_el.text or "") if title_el is not None else ""
        if not title:
            title = f"arXiv:{arxiv_id}"

        # --- Abstract (body) ---
        summary_el = entry.find("atom:summary", _NS)
        body = _clean_whitespace(summary_el.text or "") if summary_el is not None else ""
        if not body:
            return None

        # --- Publication date ---
        published_el = entry.find("atom:published", _NS)
        published_at = ""
        if published_el is not None and published_el.text:
            raw_pub = published_el.text.strip()
            # Atom published is ISO 8601, e.g. "2023-01-30T05:00:00Z"
            # Normalise to ensure the Z suffix is present
            published_at = raw_pub if raw_pub.endswith("Z") else raw_pub + "Z"
        if not published_at:
            return None

        # --- Authors ---
        author_names: list[str] = []
        for author_el in entry.findall("atom:author", _NS):
            name_el = author_el.find("atom:name", _NS)
            if name_el is not None and name_el.text:
                author_names.append(name_el.text.strip())
        author = ", ".join(author_names) if author_names else None

        return Article(
            article_id=_stable_article_id(self.source_id, canonical_url),
            source_id=self.source_id,
            url=canonical_url,
            published_at=published_at,
            retrieved_at=_now_utc_iso(),
            title=title,
            body=body,
            author=author,
            section="working_paper",
            language="en",
            tier=2,
            access="free",
            retrieval="arxiv_api",
            word_count=len(body.split()),
            raw_metadata={
                "document_type": "arxiv_preprint",
                "arxiv_id": arxiv_id,
                "primary_category": primary_category,
            },
        )
