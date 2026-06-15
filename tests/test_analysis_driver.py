"""Wiring test for the downstream analysis driver (mnd.dashboard.run, ADR-045/043).

Exercises the whole assembly path — corpus-base-rate normalization → JEL gate →
dynamics fit → stage → centroids/UMAP → similar narratives → artifact JSON — from
persisted parquet/npy, with the heavy dependencies faked: no Qwen3-8B (JEL stubbed)
and no PyMC (a fake fitter echoes the adjusted series). The JEL classifier and the
fitter have their own unit tests; here we only prove the driver glues them together
and writes valid artifacts driven by the corpus-adjusted series.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from mnd.clustering.jel_classifier import ClusterJELAssignment
from mnd.dynamics.fitting import ClusterDynamics, FitResult
import mnd.dashboard.run as driver


CFG = {
    "dynamics": {"smoothing_window_days": 7},
    "stages": {"newly_emerging_recency_weeks": 4, "growth_min_r0": 1.0},
    "reproducibility": {"global_random_seed": 42},
    "clustering": {"umap": {"n_neighbors": 15, "min_dist": 0.0, "metric": "cosine"}},
}


def _clusters_df() -> pd.DataFrame:
    """Three in-scope clusters + a noise bucket, each spanning several days."""
    rows = []
    base = pd.Timestamp("2024-01-01", tz="UTC")
    for topic, n_days, term in [(0, 30, "inflation"), (1, 20, "bank"), (2, 25, "deficit")]:
        for d in range(n_days):
            aid = f"t{topic}_{d}"
            rows.append(dict(
                article_id=aid, topic=topic, chunk_index=0,
                source_id=["federalreserve", "imf", "cbo"][d % 3],
                url=f"http://x/{aid}",
                published_at=(base + pd.Timedelta(days=d)).isoformat(),
                title=f"{term} report {d}", body=f"{term} {term} pressures and policy {d}",
            ))
    # noise rows interleaved across the whole span (denominator participants)
    for d in range(40):
        aid = f"noise_{d}"
        rows.append(dict(
            article_id=aid, topic=-1, chunk_index=0, source_id="voxeu",
            url=f"http://x/{aid}",
            published_at=(base + pd.Timedelta(days=d)).isoformat(),
            title=f"misc {d}", body="unrelated commentary",
        ))
    return pd.DataFrame(rows)


def _topic_info() -> pd.DataFrame:
    return pd.DataFrame({
        "Topic": [0, 1, 2, -1],
        "Count": [30, 20, 25, 40],
        "Name": ["0_inflation", "1_bank", "2_deficit", "-1_noise"],
        "Representation": [
            ["inflation", "prices", "cpi"],
            ["bank", "deposits", "liquidity"],
            ["deficit", "debt", "fiscal"],
            ["misc"],
        ],
    })


class _FakeFitter:
    """Returns a converged growth-stage ClusterDynamics echoing the input series."""

    def fit_cluster(self, cluster_id, daily_counts):
        fit = FitResult(
            cluster_id=cluster_id, model_name="sir", converged=True, aicc=10.0,
            r0_mean=1.6, r0_ci_low=1.1, r0_ci_high=2.2, peak_time_mean=5.0,
            curve=[float(v) for v in daily_counts.to_numpy()],
        )
        return ClusterDynamics(
            cluster_id=cluster_id, staging_fit=fit, all_fits=[fit],
            shape_facts={"total_volume": float(daily_counts.sum()), "wave_count": 1.0},
            time_series=daily_counts, raw_series=daily_counts,
        )


def test_run_analysis_writes_adjusted_artifacts(tmp_path, monkeypatch):
    clusters_df = _clusters_df()
    clusters_path = tmp_path / "clusters.parquet"
    clusters_df.to_parquet(clusters_path, index=False)

    # Embeddings row-aligned to clusters.parquet; distinct per topic so centroids differ.
    rng = np.random.default_rng(0)
    topic_vec = {0: rng.normal(0, 1, 8), 1: rng.normal(5, 1, 8), 2: rng.normal(-5, 1, 8), -1: rng.normal(0, 1, 8)}
    emb = np.vstack([topic_vec[t] + rng.normal(0, 0.01, 8) for t in clusters_df["topic"]])
    emb_path = tmp_path / "embeddings.npy"
    np.save(str(emb_path), emb)

    ti_path = tmp_path / "topic_info.parquet"
    _topic_info().to_parquet(ti_path, index=False)

    # Stub the JEL classifier: all three clusters in-scope (its own test covers it).
    def _fake_classify(cluster_terms, **_):
        return {
            cid: ClusterJELAssignment(
                cluster_id=cid, primary_code="G", in_scope=True,
                similarity=0.8, runner_up="E", runner_up_gap=0.1,
            )
            for cid in cluster_terms
        }

    monkeypatch.setattr(driver, "classify_clusters", _fake_classify)

    out = driver.run_analysis(
        clusters_path=clusters_path,
        embeddings_path=emb_path,
        topic_info_path=ti_path,
        out_dir=tmp_path / "dash",
        cfg=CFG,
        embedder=object(),       # unused — classify is stubbed
        fitter=_FakeFitter(),
    )

    index = json.loads((out / "index.json").read_text())
    assert index["n_narratives"] == 3                 # noise excluded
    assert {e["cluster_id"] for e in index["narratives"]} == {0, 1, 2}

    # Per-narrative artifacts exist, are valid JSON, and carry the volume series.
    for cid in (0, 1, 2):
        art = json.loads((out / f"narrative_{cid}.json").read_text())
        assert art["cluster_id"] == cid
        assert len(art["volume"]["values"]) > 0
        assert art["stage"] == "growth"               # r0_mean 1.6 ≥ 1.0


def test_corpus_adjustment_indexes_to_count_units():
    """adj = raw / N̄ * N̄_mean keeps the series in count-like units (ADR-045)."""
    from mnd.dynamics.normalize import adjusted_cluster_volumes, corpus_base_rate

    df = _clusters_df()
    base, mean = corpus_base_rate(df, smoothing_window_days=7)
    assert mean > 0
    adj = adjusted_cluster_volumes(df, base_rate=base, base_rate_mean=mean, smoothing_window_days=7)
    assert set(adj) == {0, 1, 2, -1}
    # Adjusted volume is on the order of article counts, not tiny fractions.
    assert adj[0].max() > 0.1
