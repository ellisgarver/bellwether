"""Unit tests for the per-cluster extractive story card (ADR-039 companion).

Synthetic chunk + topic_info frames — no corpus, embeddings, or model needed.
Validate chunk→article folding, term-overlap ranking, source mix, peak-day,
excerpt slicing, and that noise (topic -1) is skipped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mnd.dashboard.story_card import (
    StoryCard,
    _representative_docs_from_topic_info,
    build_all_cards,
    build_story_card,
)


def _clusters_df() -> pd.DataFrame:
    rows = [
        # article a1 — two chunks, topic 0, inflation-heavy
        dict(article_id="a1", topic=0, chunk_index=0, source_id="federalreserve",
             url="http://x/a1", published_at="2023-03-09T12:00:00Z",
             title="Inflation pressures mount", body="inflation inflation prices rising"),
        dict(article_id="a1", topic=0, chunk_index=1, source_id="federalreserve",
             url="http://x/a1", published_at="2023-03-09T12:00:00Z",
             title="Inflation pressures mount", body="more on inflation outlook"),
        # article a2 — one chunk, topic 0, fewer term hits
        dict(article_id="a2", topic=0, chunk_index=0, source_id="imf",
             url="http://x/a2", published_at="2023-03-10T12:00:00Z",
             title="Growth steady", body="output gap narrows slightly"),
        # article a3 — one chunk, topic 0, same day as a1 (peak)
        dict(article_id="a3", topic=0, chunk_index=0, source_id="imf",
             url="http://x/a3", published_at="2023-03-09T08:00:00Z",
             title="Prices climb", body="prices inflation again inflation"),
        # article b1 — topic 1
        dict(article_id="b1", topic=1, chunk_index=0, source_id="nber",
             url="http://x/b1", published_at="2022-06-01T12:00:00Z",
             title="Banking stress", body="bank runs liquidity"),
        # noise
        dict(article_id="n1", topic=-1, chunk_index=0, source_id="voxeu",
             url="http://x/n1", published_at="2021-01-01T12:00:00Z",
             title="Misc", body="unrelated text"),
    ]
    return pd.DataFrame(rows)


def _topic_info() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Topic": [0, 1, -1],
            "Count": [4, 1, 1],
            "Name": ["0_inflation_prices", "1_banking_stress", "-1_noise"],
            "Representation": [
                ["inflation", "prices", "outlook"],
                ["bank", "liquidity"],
                ["misc"],
            ],
        }
    )


class TestBuildStoryCard:
    def test_folds_chunks_to_articles(self):
        card = build_story_card(0, _clusters_df(), _topic_info())
        assert card.n_chunks == 4   # a1(2) + a2(1) + a3(1)
        assert card.n_articles == 3

    def test_label_and_terms_from_topic_info(self):
        card = build_story_card(0, _clusters_df(), _topic_info())
        assert card.label == "0_inflation_prices"
        assert card.top_terms[:2] == ["inflation", "prices"]

    def test_representative_ranked_by_term_overlap(self):
        card = build_story_card(0, _clusters_df(), _topic_info())
        # a1 (4 inflation hits across chunks + title) and a3 (2 inflation + prices)
        # should outrank a2 (no inflation/prices terms).
        titles = [a["title"] for a in card.representative_articles]
        assert titles[0] == "Inflation pressures mount"
        assert "Growth steady" == titles[-1]
        assert card.representative_articles[0]["term_overlap"] >= card.representative_articles[-1]["term_overlap"]

    def test_source_mix_counts_articles_not_chunks(self):
        card = build_story_card(0, _clusters_df(), _topic_info())
        mix = dict(card.source_mix)
        assert mix["federalreserve"] == 1   # a1 has 2 chunks but 1 article
        assert mix["imf"] == 2               # a2 + a3

    def test_peak_and_date_range(self):
        card = build_story_card(0, _clusters_df(), _topic_info())
        assert card.date_range == ("2023-03-09", "2023-03-10")
        assert card.peak_date == "2023-03-09"   # a1 + a3 share the day

    def test_excerpt_truncates_on_word_boundary(self):
        card = build_story_card(0, _clusters_df(), _topic_info(), excerpt_chars=10)
        ex = card.representative_articles[0]["excerpt"]
        assert ex.endswith("…")
        assert len(ex) <= 11   # 10 chars cut to a word boundary + ellipsis

    def test_missing_topic_info_falls_back(self):
        card = build_story_card(0, _clusters_df(), topic_info=None)
        assert card.label == "Cluster 0"
        assert card.top_terms == []
        # With no terms, representatives still returned (overlap all zero).
        assert card.n_articles == 3

    def test_empty_cluster_returns_shell(self):
        card = build_story_card(99, _clusters_df(), _topic_info())
        assert isinstance(card, StoryCard)
        assert card.n_articles == 0
        assert card.representative_articles == []


class TestBuildAllCards:
    def test_skips_noise_and_sorts_by_size(self):
        cards = build_all_cards(_clusters_df(), _topic_info())
        ids = [c.cluster_id for c in cards]
        assert -1 not in ids
        assert ids == [0, 1]   # topic 0 (3 articles) before topic 1 (1 article)

    def test_n_per_bucket_caps_each_panel(self):
        cards = build_all_cards(_clusters_df(), _topic_info(), n_per_bucket=1)
        assert len(cards[0].central_articles) == 1
        assert len(cards[0].representative_articles) == 1  # alias of central
        assert len(cards[0].earliest_articles) <= 1
        assert len(cards[0].newest_articles) <= 1

    def test_panels_are_deduplicated(self):
        # No article appears in more than one panel.
        card = build_story_card(0, _clusters_df(), _topic_info(), n_per_bucket=3)
        seen = [a["title"] for a in card.central_articles + card.earliest_articles + card.newest_articles]
        assert len(seen) == len(set(seen))


class TestRepresentativeDocs:
    """JEL representation enrichment helper (ADR-055)."""

    @staticmethod
    def _ti(docs_value) -> pd.DataFrame:
        return pd.DataFrame(
            {"Topic": [0], "Count": [3], "Name": ["0_inflation"], "Representative_Docs": [docs_value]}
        )

    def test_returns_excerpts_from_list(self):
        out = _representative_docs_from_topic_info(
            self._ti(["Fed signals a pause in rate hikes.", "Inflation cools to target."]), 0
        )
        assert out == ["Fed signals a pause in rate hikes.", "Inflation cools to target."]

    def test_handles_ndarray_roundtrip(self):
        # Parquet round-trips the list into an object ndarray (the JEL-bug shape).
        arr = np.array(["A representative macro document about r-star."], dtype=object)
        out = _representative_docs_from_topic_info(self._ti(arr), 0)
        assert out == ["A representative macro document about r-star."]

    def test_caps_at_n_docs(self):
        docs = [f"Distinct representative document number {i}." for i in range(5)]
        out = _representative_docs_from_topic_info(self._ti(docs), 0, n_docs=2)
        assert len(out) == 2

    def test_excerpts_long_doc_on_word_boundary(self):
        out = _representative_docs_from_topic_info(
            self._ti(["word " * 200]), 0, max_chars=20
        )
        assert out[0].endswith("…")
        assert len(out[0]) <= 21

    def test_missing_column_returns_empty(self):
        ti = pd.DataFrame({"Topic": [0], "Name": ["0_x"], "Representation": [["x"]]})
        assert _representative_docs_from_topic_info(ti, 0) == []

    def test_missing_topic_returns_empty(self):
        assert _representative_docs_from_topic_info(self._ti(["doc"]), 99) == []

    def test_none_topic_info_returns_empty(self):
        assert _representative_docs_from_topic_info(None, 0) == []
