"""Smoke tests for filtering stage (ADR-019: keyword-only, no embedding gate)."""
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


MACRO_ARTICLE = _make_article(
    "a1",
    "Federal Reserve raises interest rates amid inflation concerns",
    "The FOMC voted to raise the federal funds rate by 25 basis points. "
    "Inflation remains above the 2 percent target. Monetary policy tightening "
    "is expected to continue. Central bank officials cited sticky core CPI "
    "and resilient labor markets as reasons for the rate hike.",
)

OFF_TOPIC_ARTICLE = _make_article(
    "a2",
    "Apple announces new iPhone model with improved battery",
    "Apple unveiled its latest smartphone at a press event. The new device "
    "features an improved camera system and longer battery life. Sales are "
    "expected to be strong in the holiday quarter.",
)


class TestTopicFilter:
    """Per ADR-019, the topic filter is keyword-only — the embedding-similarity
    Gate 2 (cosine to seed-article centroid, threshold 0.55) was removed
    because no field-accepted literature anchor exists for a fixed cosine
    cutoff in dense-retrieval filtering."""

    def test_macro_article_passes_keyword_gate(self):
        from mnd.filtering.topic_filter import _keyword_gate, _load_keywords
        from mnd.utils.config import load_yaml

        kw_yaml = load_yaml("config/topic_filter_keywords.yaml")
        keywords = _load_keywords(kw_yaml)
        text = f"{MACRO_ARTICLE.title} {MACRO_ARTICLE.body}"
        passed, count = _keyword_gate(text, keywords, min_matches=2)
        assert passed, f"expected keyword gate to pass; got count={count}"
        assert count >= 2

    def test_off_topic_article_fails_keyword_gate(self):
        from mnd.filtering.topic_filter import _keyword_gate, _load_keywords
        from mnd.utils.config import load_yaml

        kw_yaml = load_yaml("config/topic_filter_keywords.yaml")
        keywords = _load_keywords(kw_yaml)
        text = f"{OFF_TOPIC_ARTICLE.title} {OFF_TOPIC_ARTICLE.body}"
        passed, count = _keyword_gate(text, keywords, min_matches=2)
        assert not passed, f"expected keyword gate to fail; got count={count}"

    def test_filter_sets_metadata_fields(self):
        from mnd.filtering.topic_filter import TopicFilter

        tf = TopicFilter()
        articles = [
            _make_article(a.article_id, a.title, a.body)
            for a in (MACRO_ARTICLE, OFF_TOPIC_ARTICLE)
        ]
        tf.filter(articles)
        for a in articles:
            assert "passed_filter" in a.raw_metadata
            assert "filter_detail" in a.raw_metadata
            assert "keyword_matches" in a.raw_metadata["filter_detail"]
            assert "keyword_pass" in a.raw_metadata["filter_detail"]

    def test_macro_article_passes_keyword_only_filter(self):
        from mnd.filtering.topic_filter import TopicFilter

        tf = TopicFilter()
        arts = [_make_article("m1", MACRO_ARTICLE.title, MACRO_ARTICLE.body)]
        tf.filter(arts)
        assert arts[0].raw_metadata["passed_filter"] is True

    def test_off_topic_article_fails_keyword_only_filter(self):
        from mnd.filtering.topic_filter import TopicFilter

        tf = TopicFilter()
        arts = [_make_article("o1", OFF_TOPIC_ARTICLE.title, OFF_TOPIC_ARTICLE.body)]
        tf.filter(arts)
        assert arts[0].raw_metadata["passed_filter"] is False


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
