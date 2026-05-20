"""Smoke tests for filtering stage (ADR-020: dedup only — no topic filter)."""
from __future__ import annotations

from datetime import datetime

import pytest

from mnd.ingestion.base import Article


def _make_article(article_id: str, title: str, body: str, dt: datetime | None = None) -> Article:
    dt = dt or datetime(2024, 1, 15)
    return Article(
        article_id=article_id,
        source_id="wsj",
        url=f"https://wsj.com/{article_id}",
        published_at=dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        retrieved_at=dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        title=title,
        body=body,
    )


def test_topic_filter_module_removed():
    """ADR-020: the pre-clustering JEL keyword filter has been removed.

    Importing it must fail so future code can't accidentally reintroduce
    a researcher-derived keyword gate.
    """
    with pytest.raises(ImportError):
        from mnd.filtering.topic_filter import TopicFilter  # noqa: F401


def test_filtering_init_exports_only_deduplicator():
    """`from mnd.filtering import *` should yield Deduplicator only (ADR-020)."""
    import mnd.filtering as f

    assert "Deduplicator" in f.__all__
    assert "TopicFilter" not in f.__all__


datasketch = pytest.importorskip("datasketch", reason="datasketch not installed; run pip install -r requirements.txt")


class TestDeduplicator:
    def test_exact_duplicate_removed(self):
        from mnd.filtering.dedup import Deduplicator

        title = "Fed raises rates by 25 basis points amid inflation"
        body = "The Federal Reserve raised interest rates. Inflation above target."
        a1 = _make_article("dup1", title, body, datetime(2024, 1, 10))
        a2 = _make_article("dup2", title, body, datetime(2024, 1, 10, 2))

        dedup = Deduplicator(threshold=0.85, window_hours=48, num_perm=64)
        unique = dedup.deduplicate([a1, a2])
        assert len(unique) == 1

    def test_distinct_articles_both_kept(self):
        from mnd.filtering.dedup import Deduplicator

        a1 = _make_article(
            "d1",
            "Fed raises rates",
            "The Federal Reserve raised interest rates by 25 basis points today.",
            datetime(2024, 1, 10),
        )
        a2 = _make_article(
            "d2",
            "Housing market cools",
            "Home sales declined sharply as mortgage rates climbed above 7 percent.",
            datetime(2024, 1, 10, 3),
        )
        dedup = Deduplicator(threshold=0.85, window_hours=48, num_perm=64)
        unique = dedup.deduplicate([a1, a2])
        assert len(unique) == 2

    def test_outside_window_not_deduplicated(self):
        """Two near-duplicates published >48h apart should both be kept."""
        from mnd.filtering.dedup import Deduplicator

        body = "Federal Reserve raises interest rates by 25 basis points amid elevated inflation."
        a1 = _make_article("w1", "Rate hike", body, datetime(2024, 1, 10))
        a2 = _make_article("w2", "Rate hike", body, datetime(2024, 1, 13))  # 72h later

        dedup = Deduplicator(threshold=0.85, window_hours=48, num_perm=64)
        unique = dedup.deduplicate([a1, a2])
        assert len(unique) == 2

    def test_metadata_set_on_all_articles(self):
        from mnd.filtering.dedup import Deduplicator

        articles = [
            _make_article("x1", "Inflation surges", "Inflation hit 9.1 percent in June.", datetime(2024, 1, 10)),
            _make_article("x2", "Stocks fall", "Stock market declined sharply amid rate fears.", datetime(2024, 1, 10)),
        ]
        Deduplicator(threshold=0.85, window_hours=48, num_perm=64).deduplicate(articles)
        for a in articles:
            assert "is_duplicate" in a.raw_metadata
