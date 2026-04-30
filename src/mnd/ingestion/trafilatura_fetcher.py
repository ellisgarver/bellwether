"""Full-text fetcher for free-access outlets discovered by GDELT.

GDELT is metadata-only (body=""). This module fills in the body for any
Article with retrieval="gdelt_url" by fetching the page and running
trafilatura's extraction pipeline.

trafilatura is purpose-built for news article extraction: it handles
boilerplate removal, paywall detection, and encoding normalization better
than raw BeautifulSoup. We prefer it over lxml + custom selectors for
non-Fed sources.

Usage (typically called right after GdeltIngestor.fetch):
    from mnd.ingestion.trafilatura_fetcher import fetch_free_outlet_bodies
    articles = fetch_free_outlet_bodies(gdelt_articles, min_words=200)
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Iterator

import trafilatura
from trafilatura.settings import use_config

from mnd.ingestion.base import Article, _now_utc_iso
from mnd.utils.logging import get_logger

log = get_logger(__name__)

_USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"

# trafilatura config: use a custom UA, raise timeout slightly
_TRAFILATURA_CFG = use_config()
_TRAFILATURA_CFG.set("DEFAULT", "USER_AGENTS", _USER_AGENT)
_TRAFILATURA_CFG.set("DEFAULT", "DOWNLOAD_TIMEOUT", "20")


def _download_html(url: str) -> str | None:
    """Download page HTML, trying trafilatura's fetcher then requests as fallback."""
    import requests as _requests

    # trafilatura's own downloader handles encoding and some anti-bot headers
    try:
        html = trafilatura.fetch_url(url, config=_TRAFILATURA_CFG)
        if html:
            return html
    except Exception:
        pass

    # Fallback: plain requests with our UA
    try:
        resp = _requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=20)
        if resp.status_code == 200 and resp.text:
            return resp.text
    except Exception:
        pass

    return None


def _fetch_one(article: Article, min_words: int) -> Article | None:
    """Fetch and extract body for a single Article. Returns None on failure."""
    html = _download_html(article.url)
    if not html:
        log.debug("Could not download %s", article.url)
        return None

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
        favor_recall=True,
        config=_TRAFILATURA_CFG,
    )
    if not text or len(text.split()) < min_words:
        log.debug(
            "Body too short (%d words) for %s",
            len(text.split()) if text else 0,
            article.url,
        )
        return None

    return Article(
        article_id=article.article_id,
        source_id=article.source_id,
        url=article.url,
        published_at=article.published_at,
        retrieved_at=_now_utc_iso(),
        title=article.title,
        body=text,
        author=article.author,
        section=article.section,
        language=article.language,
        tier=article.tier,
        access=article.access,
        retrieval="trafilatura",
        word_count=len(text.split()),
        raw_metadata={**article.raw_metadata, "trafilatura_fetched": True},
    )


def fetch_free_outlet_bodies(
    articles: Iterable[Article],
    *,
    min_words: int = 200,
    max_workers: int = 4,
    inter_request_delay: float = 1.0,
) -> Iterator[Article]:
    """Yield articles with body text filled in via trafilatura.

    Only processes articles where retrieval=="gdelt_url" and body is empty.
    Articles that can't be fetched or are too short are dropped.
    Articles that already have a body (e.g. Fed documents) are passed through.

    Args:
        articles: Stream of Article records (typically from GdeltIngestor).
        min_words: Drop articles whose extracted body has fewer than this many words.
        max_workers: Thread pool size for concurrent HTTP fetches.
        inter_request_delay: Seconds to sleep between each fetch within a thread.
            Keeps per-outlet request rate polite.
    """
    needs_fetch: list[Article] = []
    already_filled: list[Article] = []

    for a in articles:
        if a.retrieval == "gdelt_url" and not a.body.strip():
            needs_fetch.append(a)
        else:
            already_filled.append(a)

    log.info(
        "Free-outlet fetcher: %d articles need full text, %d already have body",
        len(needs_fetch),
        len(already_filled),
    )

    yield from already_filled

    if not needs_fetch:
        return

    def _worker(art: Article) -> Article | None:
        result = _fetch_one(art, min_words)
        if inter_request_delay > 0:
            time.sleep(inter_request_delay)
        return result

    n_ok = 0
    n_fail = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_worker, art): art for art in needs_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                n_ok += 1
                yield result
            else:
                n_fail += 1

    log.info(
        "Free-outlet fetcher: %d fetched successfully, %d dropped (fetch failure or too short)",
        n_ok,
        n_fail,
    )
