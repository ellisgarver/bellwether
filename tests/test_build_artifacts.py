"""Unit tests for the dashboard artifact builder (ADR-043 / ADR-044).

Synthetic pipeline objects — no corpus, embeddings, PyMC, FRED, or Media Cloud.
Validate that the builder assembles a clean DashboardIndex + per-narrative
NarrativeArtifacts, derives story cards + semantic map edges, passes fit curves
through ("curves not parameters"), computes the emerging flag against the corpus
frontier, excludes noise, and writes strictly-valid (NaN-free) JSON.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from mnd.dashboard.artifacts import SCHEMA_VERSION
from mnd.dashboard.build_artifacts import (
    build_dashboard_artifacts,
    write_dashboard_artifacts,
)
from mnd.clustering.jel_classifier import ClusterJELAssignment
from mnd.dynamics.fitting import ClusterDynamics, FitResult
from mnd.stages.classify import StageClassification


CFG = {
    "stages": {"newly_emerging_recency_weeks": 4, "growth_min_r0": 1.0},
    "reproducibility": {"global_random_seed": 42},
}


def _clusters_df() -> pd.DataFrame:
    rows = [
        dict(article_id="a1", topic=0, chunk_index=0, source_id="federalreserve",
             url="http://x/a1", published_at="2023-03-09T12:00:00Z",
             title="Inflation pressures mount", body="inflation inflation prices rising"),
        dict(article_id="a2", topic=0, chunk_index=0, source_id="imf",
             url="http://x/a2", published_at="2023-03-10T12:00:00Z",
             title="Growth steady", body="output gap narrows slightly"),
        dict(article_id="b1", topic=1, chunk_index=0, source_id="nber",
             url="http://x/b1", published_at="2022-06-01T12:00:00Z",
             title="Banking stress", body="bank runs liquidity"),
        dict(article_id="n1", topic=-1, chunk_index=0, source_id="voxeu",
             url="http://x/n1", published_at="2021-01-01T12:00:00Z",
             title="Misc", body="unrelated text"),
    ]
    return pd.DataFrame(rows)


def _topic_info() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Topic": [0, 1, -1],
            "Count": [2, 1, 1],
            "Name": ["0_inflation_prices", "1_banking_stress", "-1_noise"],
            "Representation": [["inflation", "prices"], ["bank", "liquidity"], ["misc"]],
        }
    )


def _dynamics() -> dict[int, ClusterDynamics]:
    s0 = pd.Series([2.0, 1.0], index=["2023-03-09", "2023-03-10"])
    s1 = pd.Series([1.0], index=["2022-06-01"])
    log0 = FitResult(
        cluster_id=0, model_name="logistic", converged=True, aicc=12.3,
        r0_mean=1.8, r0_ci_low=1.2, r0_ci_high=2.4, peak_time_mean=1.0,
        curve=[1.5, 1.0],
    )
    sir0 = FitResult(
        cluster_id=0, model_name="sir", converged=True, aicc=11.0,
        r0_mean=2.0, r0_ci_low=1.5, r0_ci_high=2.6, peak_time_mean=1.0,
        curve=[1.4, 1.1],
    )
    # cluster 1: a failed fit — aicc stays inf, no curve, no R0.
    fail1 = FitResult(
        cluster_id=1, model_name="sir", converged=False,
        failure_reason="low ESS",
    )
    return {
        0: ClusterDynamics(
            cluster_id=0, staging_fit=sir0, all_fits=[log0, sir0],
            shape_facts={"total_volume": 3.0, "wave_count": 1.0},
            time_series=s0, raw_series=s0,
        ),
        1: ClusterDynamics(
            cluster_id=1, staging_fit=fail1, all_fits=[fail1],
            shape_facts={"total_volume": 1.0, "wave_count": 1.0},
            time_series=s1, raw_series=s1,
        ),
    }


def _stages() -> dict[int, StageClassification]:
    return {
        0: StageClassification(0, "growth", 2.0, 1.5, 2.6, 1.0, 2, {"converged": True}),
        1: StageClassification(1, "dormant", None, None, None, None, 1, {"converged": False}),
    }


def _jel() -> dict[int, ClusterJELAssignment]:
    return {
        0: ClusterJELAssignment(0, "E", 0.71, "G", 0.05, True),
        1: ClusterJELAssignment(1, "G", 0.66, "E", 0.03, True),
    }


def _centroids() -> tuple[list[int], np.ndarray]:
    # Two nearly-orthogonal centroids → low but positive cosine edge.
    return [0, 1], np.array([[1.0, 0.0], [0.6, 0.8]], dtype=float)


def _build(**overrides):
    ids, cents = _centroids()
    kwargs = dict(
        clusters_df=_clusters_df(),
        dynamics=_dynamics(),
        stages=_stages(),
        topic_info=_topic_info(),
        jel=_jel(),
        ordered_cluster_ids=ids,
        centroids=cents,
        umap_xy={0: (0.1, 0.2), 1: (0.9, -0.3)},
        cfg=CFG,
        generated_at="2023-03-11T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return build_dashboard_artifacts(**kwargs)


class TestBuild:
    def test_one_artifact_per_nonnoise_cluster(self):
        index, narratives = _build()
        assert index.n_narratives == 2
        assert {n.cluster_id for n in narratives} == {0, 1}
        # noise topic -1 never appears
        assert all(n.cluster_id != -1 for n in narratives)

    def test_volume_series_from_raw(self):
        _, narratives = _build()
        n0 = next(n for n in narratives if n.cluster_id == 0)
        assert n0.volume.dates == ["2023-03-09", "2023-03-10"]
        assert n0.volume.values == [2.0, 1.0]
        assert n0.volume.freq == "D"

    def test_fit_curves_passed_through(self):
        _, narratives = _build()
        n0 = next(n for n in narratives if n.cluster_id == 0)
        sir = next(f for f in n0.fits if f.model == "sir")
        assert sir.curve == [1.4, 1.1]
        assert sir.r0_ci == (1.5, 2.6)
        assert n0.staging_model == "sir"

    def test_failed_fit_has_null_aicc_and_no_curve(self):
        _, narratives = _build()
        n1 = next(n for n in narratives if n.cluster_id == 1)
        fit = n1.fits[0]
        assert fit.aicc is None          # inf scrubbed
        assert fit.curve is None
        assert fit.failure_reason == "low ESS"
        assert fit.r0_ci is None

    def test_semantic_edges_with_cosine_weight(self):
        index, _ = _build()
        e0 = next(e for e in index.narratives if e.cluster_id == 0)
        assert len(e0.similar_edges) == 1
        neighbor, weight = e0.similar_edges[0]
        assert neighbor == 1
        assert weight == pytest.approx(0.6, abs=1e-9)  # [1,0]·[0.6,0.8]

    def test_no_edges_without_centroids(self):
        index, _ = _build(centroids=None, ordered_cluster_ids=None)
        assert all(e.similar_edges == [] for e in index.narratives)

    def test_emerging_against_frontier(self):
        index, _ = _build()
        e0 = next(e for e in index.narratives if e.cluster_id == 0)
        e1 = next(e for e in index.narratives if e.cluster_id == 1)
        assert e0.is_emerging is True    # onset 2023-03-09, frontier 2023-03-10
        assert e1.is_emerging is False   # onset 2022-06-01

    def test_jel_passthrough(self):
        index, narratives = _build()
        n0 = next(n for n in narratives if n.cluster_id == 0)
        assert n0.jel is not None and n0.jel.code == "E" and n0.jel.in_scope
        e0 = next(e for e in index.narratives if e.cluster_id == 0)
        assert e0.jel_code == "E" and e0.in_scope is True

    def test_umap_passthrough(self):
        index, _ = _build()
        e0 = next(e for e in index.narratives if e.cluster_id == 0)
        assert e0.umap_xy == (0.1, 0.2)

    def test_index_sorted_by_size(self):
        index, _ = _build()
        ns = [e.n_articles for e in index.narratives]
        assert ns == sorted(ns, reverse=True)
        assert index.narratives[0].cluster_id == 0   # 2 articles > 1

    def test_index_run_metadata(self):
        index, _ = _build()
        assert index.global_random_seed == 42
        assert index.stage_min_r0 == 1.0
        assert index.schema_version == SCHEMA_VERSION
        assert index.generated_at == "2023-03-11T00:00:00+00:00"

    def test_missing_optional_inputs_degrade(self):
        # No jel, umap, overlays, centroids → still builds, fields default.
        index, narratives = _build(
            jel=None, umap_xy=None, centroids=None, ordered_cluster_ids=None
        )
        n0 = next(n for n in narratives if n.cluster_id == 0)
        assert n0.jel is None and n0.markets is None and n0.mediacloud is None
        e0 = next(e for e in index.narratives if e.cluster_id == 0)
        assert e0.in_scope is True and e0.jel_code is None and e0.umap_xy is None


class TestWrite:
    def test_writes_valid_json_files(self, tmp_path):
        index, narratives = _build()
        out = write_dashboard_artifacts(index, narratives, tmp_path)

        idx = json.loads((out / "index.json").read_text())
        assert idx["n_narratives"] == 2
        assert len(idx["narratives"]) == 2

        # per-narrative files exist and parse; inf aicc became null (strict JSON).
        n1 = json.loads((out / "narrative_1.json").read_text())
        assert n1["fits"][0]["aicc"] is None
        n0 = json.loads((out / "narrative_0.json").read_text())
        assert n0["cluster_id"] == 0
        assert n0["volume"]["values"] == [2.0, 1.0]

    def test_no_nan_tokens_in_output(self, tmp_path):
        index, narratives = _build()
        out = write_dashboard_artifacts(index, narratives, tmp_path)
        for f in out.glob("*.json"):
            text = f.read_text()
            assert "NaN" not in text and "Infinity" not in text
