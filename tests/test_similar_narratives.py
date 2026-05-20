"""Unit tests for ADR-019 section H similar-narrative finder."""
from __future__ import annotations

import numpy as np
import pandas as pd

from mnd.clustering.similar_narratives import (
    compute_similar_narratives,
    lexical_similarity,
    morphological_similarity,
    semantic_similarity,
)


class TestSemantic:
    def test_identical_centroids_rank_first(self):
        # Cluster 0 and 1 have the same centroid -- they should be each other's top-1
        centroids = np.array(
            [
                [1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ]
        )
        result = semantic_similarity([0, 1, 2, 3], centroids, top_k=2)
        assert result[0][0] == 1
        assert result[1][0] == 0

    def test_self_excluded(self):
        centroids = np.eye(4)
        result = semantic_similarity([10, 20, 30, 40], centroids, top_k=3)
        for cid, neighbors in result.items():
            assert cid not in neighbors

    def test_zero_norm_centroid_does_not_crash(self):
        centroids = np.array([[1.0, 0.0], [0.0, 0.0], [0.0, 1.0]])
        result = semantic_similarity([0, 1, 2], centroids, top_k=2)
        assert 0 in result and 1 in result and 2 in result


class TestLexical:
    def test_identical_term_sets_yield_jaccard_one(self):
        terms = {
            0: ["fed", "rate", "policy"],
            1: ["fed", "rate", "policy"],
            2: ["bank", "stress", "deposit"],
        }
        result = lexical_similarity([0, 1, 2], terms, top_k=1)
        assert result[0] == [1]
        assert result[1] == [0]

    def test_disjoint_sets_get_lowest_rank(self):
        # Cluster 0 has partial overlap with 1, none with 2
        terms = {
            0: ["a", "b", "c"],
            1: ["a", "d"],
            2: ["x", "y", "z"],
        }
        result = lexical_similarity([0, 1, 2], terms, top_k=2)
        assert result[0][0] == 1

    def test_empty_term_set_handled(self):
        terms = {0: [], 1: ["a"], 2: ["b"]}
        result = lexical_similarity([0, 1, 2], terms, top_k=2)
        assert 0 in result


class TestMorphological:
    def test_identical_shape_ranks_first(self):
        idx = pd.date_range("2023-01-01", periods=10, freq="W")
        curves = {
            0: pd.Series(np.arange(10, dtype=float), index=idx),
            1: pd.Series(np.arange(10, dtype=float) * 2 + 5, index=idx),  # same shape
            2: pd.Series(np.arange(10, dtype=float)[::-1], index=idx),    # reversed
        }
        result = morphological_similarity([0, 1, 2], curves, top_k=2)
        assert result[0][0] == 1

    def test_disjoint_time_ranges_compared_on_shape(self):
        # Two clusters whose lifespans don't overlap but share morphology
        idx_a = pd.date_range("2020-01-01", periods=8, freq="W")
        idx_b = pd.date_range("2023-01-01", periods=8, freq="W")
        bump = np.array([0, 1, 3, 8, 5, 2, 1, 0], dtype=float)
        curves = {
            0: pd.Series(bump, index=idx_a),
            1: pd.Series(bump, index=idx_b),
            2: pd.Series(np.zeros(8), index=idx_a),
        }
        result = morphological_similarity([0, 1, 2], curves, top_k=1)
        assert result[0] == [1]


class TestComputeBundle:
    def test_returns_three_measures_per_cluster(self):
        centroids = np.eye(3)
        terms = {0: ["a"], 1: ["a", "b"], 2: ["c"]}
        idx = pd.date_range("2023-01-01", periods=5, freq="W")
        curves = {cid: pd.Series(np.arange(5, dtype=float), index=idx) for cid in [0, 1, 2]}

        out = compute_similar_narratives(
            [0, 1, 2],
            centroids=centroids,
            top_terms=terms,
            volume_curves=curves,
            top_k=2,
        )
        for cid in [0, 1, 2]:
            assert set(out[cid].keys()) == {"semantic", "lexical", "morphological"}
            for measure in out[cid].values():
                assert len(measure) <= 2
                assert cid not in measure
