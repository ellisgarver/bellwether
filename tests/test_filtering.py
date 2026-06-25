"""Smoke tests for filtering stage (ADR-020: dedup only — no topic filter)."""
from __future__ import annotations

from datetime import datetime

import pytest

from mnd.filtering.boilerplate import BoilerplateStripper
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


def test_filtering_init_exports_dedup_and_boilerplate():
    """Filtering exports the two content/repetition operators, never a topic gate (ADR-020)."""
    import mnd.filtering as f

    assert "Deduplicator" in f.__all__
    assert "BoilerplateStripper" in f.__all__
    assert "TopicFilter" not in f.__all__


class TestBoilerplateStripper:
    """Cross-document recurring-passage removal (ADR-054)."""

    BOILER = "The views expressed are those of the author and do not reflect the institution."

    def test_recurring_sentence_stripped_unique_content_survives(self):
        articles = [
            _make_article(f"c{i}", "t", f"Distinct macro analysis paragraph number {i} on inflation. {self.BOILER}")
            for i in range(4)
        ]
        stripper = BoilerplateStripper(min_doc_frequency=3, min_sentence_words=6, min_content_words=2)
        kept = stripper.strip(articles)

        assert len(kept) == 4
        for i, a in enumerate(kept):
            assert "views expressed" not in a.body.lower()
            assert f"number {i}" in a.body
        assert stripper.report.n_boilerplate_sentences == 1
        assert stripper.report.n_instances_removed == 4
        assert stripper.report.n_articles_modified == 4
        assert stripper.report.top_boilerplate[0]["doc_frequency"] == 4

    def test_short_repeated_sentence_not_stripped(self):
        articles = [_make_article(f"s{i}", "t", "Rates rose. Markets fell.") for i in range(5)]
        stripper = BoilerplateStripper(min_doc_frequency=3, min_sentence_words=6, min_content_words=2)
        kept = stripper.strip(articles)

        assert len(kept) == 5
        assert stripper.report.n_boilerplate_sentences == 0
        assert all("Rates rose" in a.body for a in kept)

    def test_content_free_shell_dropped_short_clean_article_kept(self):
        content = [
            _make_article(f"k{i}", "t", f"A genuinely distinct sentence about fiscal policy {i} here. {self.BOILER}")
            for i in range(3)
        ]
        shell = _make_article("shell", "t", self.BOILER)
        short_clean = _make_article("short", "t", "Tiny note.")
        stripper = BoilerplateStripper(min_doc_frequency=3, min_sentence_words=6, min_content_words=4)
        kept = stripper.strip(content + [shell, short_clean])

        kept_ids = {a.article_id for a in kept}
        assert "shell" not in kept_ids
        assert "short" in kept_ids
        assert stripper.report.n_articles_dropped == 1
        assert stripper.report.dropped_article_ids == ["shell"]
        assert stripper.report.n_articles_modified == 3

    def test_word_count_recomputed_on_strip(self):
        a = _make_article("w", "t", f"One distinct macroeconomic observation about output gaps. {self.BOILER}")
        others = [_make_article(f"o{i}", "t", f"Other distinct line {i} on credit spreads. {self.BOILER}") for i in range(3)]
        stripper = BoilerplateStripper(min_doc_frequency=3, min_sentence_words=6, min_content_words=2)
        kept = stripper.strip([a, *others])

        cleaned = next(x for x in kept if x.article_id == "w")
        assert cleaned.word_count == len(cleaned.body.split())
        assert cleaned.word_count > 0

    def test_disabled_is_passthrough(self):
        articles = [_make_article(f"p{i}", "t", f"Repeated. {self.BOILER}") for i in range(5)]
        stripper = BoilerplateStripper(enabled=False, min_doc_frequency=2)
        kept = stripper.strip(articles)

        assert len(kept) == 5
        assert all("views expressed" in a.body.lower() for a in kept)
        assert stripper.report.n_boilerplate_sentences == 0

    def test_from_config_reads_block(self):
        cfg = {"filtering": {"boilerplate": {
            "enabled": True, "min_doc_frequency": 7, "min_sentence_words": 4, "min_content_words": 9,
        }}}
        stripper = BoilerplateStripper.from_config(cfg)
        assert stripper.min_doc_frequency == 7
        assert stripper.min_sentence_words == 4
        assert stripper.min_content_words == 9

    def test_from_config_defaults_when_absent(self):
        stripper = BoilerplateStripper.from_config({})
        assert stripper.enabled is True
        assert stripper.min_doc_frequency == 25


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
