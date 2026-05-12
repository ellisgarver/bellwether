"""Tier 4 open journalism ingestor: Reuters.

Reuters replaces MarketWatch in the Tier 4 semantic corpus (see ADR in
docs/architecture_decisions.md). Reuters provides broad wire and analytical
macro-financial coverage at high volume and with strong Wayback CDX coverage
for the historical period.

ReutersIngestor
  Wire + analytical macro journalism. Fully open until ~2023.
  Historical (2010–2022): Wayback CDX on reuters.com URL patterns.
  Phase 6 live (2023–present): Reuters RSS feeds.

  URL patterns in Wayback:
    reuters.com/article/...    — standard Reuters story format (all years)
    reuters.com/markets/...    — markets vertical (heavy macro coverage)
    reuters.com/business/...   — business vertical

Coverage note: Reuters was fully open until ~2023. Wayback CDX coverage for
2010–2022 is solid. From 2023 onward, Reuters moved to a partially-paywalled
model; RSS feeds provide headline + substantial snippet for open content.
Pre/post-2023 coverage asymmetry is documented in the methodology and
corpus composition QA. Treat 2010–2022 as the primary historical window
and 2023–present as a supplementary RSS layer.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import feedparser
import requests
import trafilatura
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from mnd.ingestion.base import Article, Ingestor, _now_utc_iso, _stable_article_id
from mnd.utils.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"
_HEADERS = {"User-Agent": USER_AGENT}

CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_FETCH = "https://web.archive.org/web/{timestamp}if_/{url}"

_RT_CDX_PATTERNS = [
    "reuters.com/article/",
    "reuters.com/markets/",
    "reuters.com/business/",
]
_RT_LIVE_RSS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/reuters/topNews",
]

_MIN_BODY_WORDS = 100
_PARALLEL_WORKERS = 8
_WORKER_DELAY = 0.5           # seconds between requests per worker
_CHECKPOINT_SAVE_EVERY = 50   # save checkpoint every N URLs processed
_PROGRESS_LOG_EVERY = 1000    # log progress every N URLs
_CDX_PAGE_SIZE = 5000         # rows per CDX request; showResumeKey triggers 503 on IA servers


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def _is_transient_error(exc: BaseException) -> bool:
    """Return True for errors worth retrying (transient network / server errors)."""
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else 0
        return status >= 500
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


@retry(
    retry=retry_if_exception(_is_transient_error),
    wait=wait_random_exponential(multiplier=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _reuters_cdx_get(params: dict) -> requests.Response:
    return requests.get(CDX_API, params=params, headers=_HEADERS, timeout=60.0)


@retry(
    retry=retry_if_exception(_is_transient_error),
    wait=wait_random_exponential(multiplier=1, max=20),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _reuters_wayback_get(url: str) -> requests.Response:
    resp = requests.get(url, headers=_HEADERS, timeout=45.0, allow_redirects=True)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_RT_EXCLUDE_SEGMENTS = {
    "video", "graphics", "photo", "search", "tag", "author",
}
_RT_REQUIRED_PREFIXES = ("/article/", "/markets/", "/business/")


def _is_article_url(url: str) -> bool:
    """Return True if url looks like a Reuters article (not multimedia/index/search).

    Requirements:
    - Path must contain /article/, /markets/, or /business/.
    - Final path segment must be >=20 characters (filters category index pages).
    - Path must not contain any excluded segment (video, graphics, photo, etc.).
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    path_lower = path.lower()

    # Must contain at least one of the required path prefixes.
    if not any(prefix in path_lower for prefix in _RT_REQUIRED_PREFIXES):
        return False

    # Exclude multimedia, search, taxonomy, and author pages.
    parts = set(path_lower.split("/"))
    if parts & _RT_EXCLUDE_SEGMENTS:
        return False

    # Final segment must be long enough to be a real article slug.
    segments = [s for s in path.split("/") if s]
    if not segments or len(segments[-1]) < 20:
        return False

    return True


# ---------------------------------------------------------------------------
# CDX query (chunked — avoids showResumeKey which triggers 503 on IA servers)
# ---------------------------------------------------------------------------

def _reuters_cdx_query(pattern: str, start: date, end: date) -> list[tuple[str, str]]:
    """Return deduplicated (url, timestamp) pairs from Wayback CDX for a URL prefix.

    Chunks the date range into 7-day windows to keep each CDX request small.
    showResumeKey triggers 503 on Internet Archive servers even when regular
    CDX queries succeed, so we avoid it and use date-range chunking instead.
    """
    seen: set[str] = set()
    result: list[tuple[str, str]] = []

    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=7), end)
        params = {
            "url": pattern,
            "matchType": "prefix",
            "output": "json",
            "fl": "original,timestamp,statuscode",
            "filter": "statuscode:200",
            "from": chunk_start.strftime("%Y%m%d"),
            "to": chunk_end.strftime("%Y%m%d"),
            "collapse": "urlkey",
            "limit": _CDX_PAGE_SIZE,
        }
        try:
            resp = _reuters_cdx_get(params)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as exc:
            log.warning(
                "Reuters CDX query failed for %s [%s → %s]: %s",
                pattern, chunk_start, chunk_end, exc,
            )
            chunk_start = chunk_end
            continue

        if rows:
            data_rows = rows[1:] if isinstance(rows[0], list) and rows[0][0] == "original" else rows
            chunk_count = 0
            for row in data_rows:
                if len(row) < 3:
                    continue
                url, ts, sc = row[0], row[1], row[2]
                if sc == "200" and _is_article_url(url) and url not in seen:
                    seen.add(url)
                    result.append((url, ts))
                    chunk_count += 1
            if chunk_count >= _CDX_PAGE_SIZE:
                log.warning(
                    "Reuters CDX chunk %s [%s → %s] hit limit=%d; some URLs may be missed",
                    pattern, chunk_start, chunk_end, _CDX_PAGE_SIZE,
                )

        chunk_start = chunk_end
        time.sleep(0.5)

    return result


# ---------------------------------------------------------------------------
# Wayback fetch helpers
# ---------------------------------------------------------------------------

def _fetch_archived(url: str, timestamp: str) -> str | None:
    """Fetch a Wayback archived page and extract article text. Returns None on failure."""
    archived_url = WAYBACK_FETCH.format(timestamp=timestamp, url=url)
    try:
        resp = _reuters_wayback_get(archived_url)
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


def _worker_fetch(url: str, timestamp: str) -> tuple[str, str, str | None]:
    """Worker function: sleep then fetch one archived URL. Returns (url, timestamp, body)."""
    time.sleep(_WORKER_DELAY)
    body = _fetch_archived(url, timestamp)
    return url, timestamp, body


def _fetch_parallel(
    pairs: list[tuple[str, str]],
    *,
    fetched_urls: set[str],
    checkpoint_path: Path | None,
    progress_label: str,
) -> Iterator[tuple[str, str, str]]:
    """Parallel Wayback fetch with checkpoint saves and progress logging.

    Yields (url, timestamp, body) for each successfully fetched article.
    Updates fetched_urls in-place and saves checkpoint every CHECKPOINT_SAVE_EVERY URLs.
    """
    todo = [(url, ts) for url, ts in pairs if url not in fetched_urls]
    total = len(pairs)
    skipped = total - len(todo)
    log.info(
        "%s: %d total URLs, %d already fetched (checkpoint), %d to fetch",
        progress_label, total, skipped, len(todo),
    )
    if not todo:
        return

    done = 0
    since_checkpoint = 0

    try:
        with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
            futures = {executor.submit(_worker_fetch, url, ts): (url, ts) for url, ts in todo}
            for future in as_completed(futures):
                url, ts = futures[future]
                done += 1
                if done % _PROGRESS_LOG_EVERY == 0:
                    log.info(
                        "%s progress: %d/%d URLs processed (%.1f%%)",
                        progress_label, done, len(todo), 100.0 * done / len(todo),
                    )
                try:
                    _, timestamp, body = future.result()
                except Exception as exc:
                    log.debug("%s fetch error %s: %s", progress_label, url, exc)
                    body = None
                if body:
                    fetched_urls.add(url)
                    since_checkpoint += 1
                    if since_checkpoint >= _CHECKPOINT_SAVE_EVERY:
                        _save_url_checkpoint(fetched_urls, checkpoint_path)
                        since_checkpoint = 0
                    yield url, ts, body
    finally:
        # Runs on normal completion, GeneratorExit (kill/close), or exception —
        # ensures the checkpoint reflects whatever was processed before exit.
        _save_url_checkpoint(fetched_urls, checkpoint_path)
        log.info(
            "%s: checkpoint saved (%d URLs total, %d processed this run)",
            progress_label, len(fetched_urls), done,
        )


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_url_checkpoint(checkpoint_path: Path | None) -> set[str]:
    if checkpoint_path and checkpoint_path.exists():
        try:
            urls = set(checkpoint_path.read_text(encoding="utf-8").splitlines())
            log.info(
                "Loaded checkpoint from %s: %d already-fetched URLs",
                checkpoint_path, len(urls),
            )
            return urls
        except Exception as exc:
            log.warning(
                "Could not read checkpoint %s: %s — starting fresh",
                checkpoint_path, exc,
            )
    return set()


def _save_url_checkpoint(fetched_urls: set[str], checkpoint_path: Path | None) -> None:
    if checkpoint_path:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text("\n".join(sorted(fetched_urls)), encoding="utf-8")


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

def _extract_reuters_title(body: str) -> str:
    """Heuristic: use first non-empty line of body as title."""
    first_line = body.split("\n")[0].strip()
    if len(first_line) > 10:
        return first_line[:120]
    return "Reuters article"


# ---------------------------------------------------------------------------
# Ingestor
# ---------------------------------------------------------------------------

class ReutersIngestor(Ingestor):
    """Reuters ingestor (Tier 4 — wire and analytical macro journalism).

    Reuters provides broad macro-financial wire coverage and analytical
    commentary that complements AP News. Fully open until ~2023.

    Historical (2010–2022): Wayback CDX on reuters.com URL patterns
    (/article/, /markets/, /business/). Fetches are parallelized (8 workers,
    0.5s delay per worker). Checkpoint/resume via checkpoint_path so a killed
    job can restart without re-fetching already-processed URLs.

    Phase 6 live (2023–present): fetch_live_rss() using Reuters business and
    top-news RSS feeds, which provide headline + substantial snippet for open
    content after Reuters moved to a partially-paywalled model.

    Coverage note: Reuters was fully open until ~2023. Wayback CDX coverage
    for 2010–2022 is solid. From 2023 onward, Reuters moved to a partially-
    paywalled model; RSS feeds provide the 2023-present supplement. The
    pre/post-2023 coverage asymmetry is documented in the methodology and
    corpus composition QA output. Treat 2010–2022 as the consistent historical
    window for cross-year comparison.
    """

    source_id = "reuters"

    def __init__(
        self,
        checkpoint_path: Path | None = None,
        max_urls: int | None = None,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._max_urls = max_urls  # debug: cap CDX results for testing

    def fetch(self, start: date, end: date) -> Iterator[Article]:
        """Historical ingestion via Wayback CDX for reuters.com URL patterns."""
        fetched_urls = _load_url_checkpoint(self._checkpoint_path)

        seen: set[str] = set()
        all_pairs: list[tuple[str, str]] = []
        for pattern in _RT_CDX_PATTERNS:
            log.info("Reuters CDX query: %s [%s → %s]", pattern, start, end)
            results = _reuters_cdx_query(pattern, start, end)
            log.info("Reuters CDX found %d URLs for pattern %s", len(results), pattern)
            for url, ts in results:
                if url not in seen:
                    seen.add(url)
                    all_pairs.append((url, ts))

        if self._max_urls is not None:
            all_pairs = all_pairs[: self._max_urls]
            log.info("Reuters: capped to %d URLs (max_urls debug param)", len(all_pairs))

        try:
            for url, timestamp, body in _fetch_parallel(
                all_pairs,
                fetched_urls=fetched_urls,
                checkpoint_path=self._checkpoint_path,
                progress_label="Reuters",
            ):
                if len(body.split()) < _MIN_BODY_WORDS:
                    continue
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
                    title=_extract_reuters_title(body),
                    body=body,
                    author=None,
                    section="markets",
                    language="en",
                    tier=4,
                    access="free",
                    retrieval="wayback_cdx",
                    word_count=len(body.split()),
                    raw_metadata={
                        "document_type": "reuters_article",
                        "wayback_timestamp": timestamp,
                    },
                )
        finally:
            # Belt-and-suspenders: save checkpoint if caller closes the generator
            # early (e.g. SLURM kill, KeyboardInterrupt, or test gen.close()).
            _save_url_checkpoint(fetched_urls, self._checkpoint_path)

    def fetch_live_rss(self, start: date, end: date) -> Iterator[Article]:
        """Phase 6: fetch recent Reuters articles via business and top-news RSS feeds."""
        for feed_url in _RT_LIVE_RSS:
            try:
                feed = feedparser.parse(feed_url, request_headers={"User-Agent": USER_AGENT})
            except Exception as exc:
                log.error("Reuters RSS fetch failed for %s: %s", feed_url, exc)
                continue
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
                title = entry.get("title", "Reuters article")
                try:
                    resp = requests.get(url, headers=_HEADERS, timeout=30.0)
                    body = trafilatura.extract(
                        resp.text, include_comments=False, include_tables=False
                    )
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
                    raw_metadata={"document_type": "reuters_rss_article"},
                )
                time.sleep(0.3)
