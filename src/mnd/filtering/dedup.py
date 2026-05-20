"""Near-duplicate detection using MinHash LSH.

Jaccard similarity on character 5-grams. Per ADR-019, the rolling time window
is removed by default (config.filtering.dedup.window_hours is no longer
required) — full-corpus MinHash LSH is feasible at this scale. The
``window_hours`` constructor argument is retained for callers (and tests) that
explicitly want a time-bounded window; when not provided and not in config,
the effective window is unbounded (100 years).

Configuration: config.filtering.dedup.{num_perm, threshold}. Anchored to
Broder 1997 (MinHash) and Henzinger 2006 (~0.8-0.9 Jaccard threshold band
for news near-duplicate detection).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence

from mnd.ingestion.base import Article
from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)


def _shingle(text: str, n: int = 5) -> set[str]:
    """Character n-grams of normalised text."""
    text = re.sub(r"\s+", " ", text.lower().strip())
    return {text[i : i + n] for i in range(max(0, len(text) - n + 1))}


def _make_minhash(shingles: set[str], num_perm: int):
    try:
        from datasketch import MinHash
    except ImportError as exc:
        raise ImportError("datasketch is required. `pip install datasketch`.") from exc
    m = MinHash(num_perm=num_perm)
    for s in shingles:
        m.update(s.encode("utf-8"))
    return m


def _parse_dt(iso_str: str | None) -> datetime:
    if not iso_str:
        return datetime.min
    try:
        return datetime.fromisoformat(iso_str.rstrip("Z"))
    except ValueError:
        return datetime.min


class Deduplicator:
    """Rolling-window MinHash deduplicator.

    Articles are sorted by publication time and processed in order. The LSH
    index holds only articles within the rolling window; older articles are
    evicted so the index stays compact.

    ``raw_metadata["is_duplicate"]`` is set on every input article.
    Returns only unique articles.
    """

    def __init__(
        self,
        num_perm: int | None = None,
        threshold: float | None = None,
        window_hours: int | None = None,
    ) -> None:
        cfg = load_config()
        dedup_cfg = cfg["filtering"]["dedup"]
        self.num_perm = num_perm if num_perm is not None else dedup_cfg["num_perm"]
        self.threshold = threshold if threshold is not None else dedup_cfg["threshold"]
        # window_hours removed from config by ADR-019 (full-corpus dedup feasible).
        # Default to 100 years if the caller doesn't override -- effectively
        # unbounded, but the variable still parameterizes the rolling-window code
        # path below for callers / tests that want explicit bounds.
        self.window_hours = (
            window_hours
            if window_hours is not None
            else dedup_cfg.get("window_hours", 24 * 365 * 100)
        )

    def deduplicate(self, articles: Sequence[Article]) -> list[Article]:
        """Return the unique subset; mutates raw_metadata on all inputs."""
        try:
            from datasketch import MinHashLSH
        except ImportError as exc:
            raise ImportError("datasketch is required. `pip install datasketch`.") from exc

        sorted_arts = sorted(articles, key=lambda a: a.published_at or "")
        lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)

        # window tracks (pub_time, article_id) for eviction
        window: list[tuple[datetime, str]] = []
        seen_ids: set[str] = set()
        unique: list[Article] = []

        for article in sorted_arts:
            pub_time = _parse_dt(article.published_at)
            text = f"{article.title} {article.body}"
            shingles = _shingle(text)

            if not shingles:
                article.raw_metadata["is_duplicate"] = False
                article.raw_metadata["duplicate_of"] = None
                unique.append(article)
                continue

            # Evict articles outside the rolling window
            cutoff = pub_time - timedelta(hours=self.window_hours)
            new_window = []
            for item_time, item_id in window:
                if item_time < cutoff:
                    try:
                        lsh.remove(item_id)
                    except KeyError:
                        pass
                else:
                    new_window.append((item_time, item_id))
            window = new_window

            mh = _make_minhash(shingles, self.num_perm)
            candidates = lsh.query(mh)
            is_dup = len(candidates) > 0

            article.raw_metadata["is_duplicate"] = is_dup
            article.raw_metadata["duplicate_of"] = candidates[0] if candidates else None

            if not is_dup and article.article_id not in seen_ids:
                lsh.insert(article.article_id, mh)
                window.append((pub_time, article.article_id))
                seen_ids.add(article.article_id)
                unique.append(article)

        n_removed = len(sorted_arts) - len(unique)
        log.info(
            "Dedup: removed %d/%d duplicates (threshold=%.2f, window=%dh)",
            n_removed,
            len(sorted_arts),
            self.threshold,
            self.window_hours,
        )
        return unique
