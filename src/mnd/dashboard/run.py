"""Downstream analysis driver: clusters.parquet → dashboard artifacts (ADR-043/045).

This is the seam the pipeline was missing. ``cluster`` persists ``clusters.parquet``
(+ ``topic_info.parquet``) and ``embeddings.npy``; the front end reads the small
JSON in ``paths.dashboard_artifacts``. Nothing connected the two except the
throwaway sample fabricator. ``run_analysis`` is that connection — it recomputes
the entire analysis layer from the persisted clustering, with no re-embedding
(the embed+cluster step is the only irreversible one-shot work).

Pipeline assembled here, in order:

  1. corpus-base-rate normalization of per-cluster daily volume (ADR-045) — the
     series both the fit and the dashboard use, so corpus growth no longer
     confounds either.
  2. JEL scope classification of each cluster (ADR-020); the JEL code is a
     per-narrative flag, not a gate — every non-noise cluster is carried into
     dynamics and out-of-scope ones (JEL ∉ {E,F,G,H}) are shown flagged with
     their code, not dropped (ADR-046).
  3. four-lens Bayesian dynamics fit per cluster (ADR-039) on the adjusted
     series, and R₀→stage classification (ADR-019).
  4. cluster centroids + 2-D UMAP positions + semantic/lexical/morphological
     similar-narratives (ADR-019 §H, ADR-044).
  5. assembly into the artifact contract via ``build_dashboard_artifacts`` and
     persistence via ``write_dashboard_artifacts``.

The Media Cloud (ADR-042) and markets/Granger (ADR-041) overlays are display-only,
require live API keys, and recompute from persisted artifacts independently; they
are left as a follow-on (passed through as absent here), and the front end already
handles their absence (null overlays).

``embedder`` and ``fitter`` are injectable so the assembly path is unit-testable
without loading Qwen3-8B or running PyMC; the CLI passes the real ones.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mnd.clustering.jel_classifier import classify_clusters
from mnd.clustering.similar_narratives import compute_similar_narratives
from mnd.dashboard.build_artifacts import (
    build_dashboard_artifacts,
    write_dashboard_artifacts,
)
from mnd.dashboard.story_card import NOISE_TOPIC, _terms_from_topic_info
from mnd.dynamics.fitting import DynamicsFitter
from mnd.dynamics.normalize import adjusted_cluster_volumes, corpus_base_rate
from mnd.stages.classify import classify_all
from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)


def _cluster_centroids(
    clusters_df: pd.DataFrame, embeddings: np.ndarray, ordered_ids: list[int]
) -> np.ndarray:
    """Mean chunk embedding per cluster, row-aligned to ``ordered_ids``."""
    topics = clusters_df["topic"].to_numpy()
    return np.vstack([embeddings[topics == cid].mean(axis=0) for cid in ordered_ids])


def _umap_positions(
    centroids: np.ndarray, ordered_ids: list[int], cfg: dict[str, Any]
) -> dict[int, tuple[float, float]]:
    """2-D UMAP of the cluster centroids for the narrative map (ADR-044).

    Mirrors the clustering UMAP params (cosine, min_dist) but at n_components=2 and
    seeded from the global seed for reproducibility. ``n_neighbors`` is clamped
    below the cluster count (UMAP requires n_neighbors < n_samples); with too few
    clusters for a meaningful embedding we fall back to a deterministic line.
    """
    n = len(ordered_ids)
    if n < 4:
        return {cid: (float(i), 0.0) for i, cid in enumerate(ordered_ids)}
    from umap import UMAP

    uc = cfg["clustering"]["umap"]
    seed = int(cfg["reproducibility"]["global_random_seed"])
    reducer = UMAP(
        n_components=2,
        n_neighbors=min(int(uc["n_neighbors"]), n - 1),
        min_dist=float(uc["min_dist"]),
        metric=uc["metric"],
        random_state=seed,
    )
    xy = reducer.fit_transform(centroids)
    return {cid: (float(xy[i, 0]), float(xy[i, 1])) for i, cid in enumerate(ordered_ids)}


def run_analysis(
    *,
    clusters_path: str | Path,
    embeddings_path: str | Path,
    out_dir: str | Path,
    topic_info_path: str | Path | None = None,
    cfg: dict[str, Any] | None = None,
    embedder: Any | None = None,
    fitter: DynamicsFitter | None = None,
) -> Path:
    """Recompute the analysis layer from persisted clustering and write artifacts.

    Returns the output directory. ``embedder`` must implement ``.encode(texts) ->
    np.ndarray`` (defaults to the production Qwen3 embedder); ``fitter`` defaults
    to ``DynamicsFitter.from_config()``.
    """
    cfg = cfg or load_config()
    smoothing = int(cfg["dynamics"]["smoothing_window_days"])

    clusters_df = pd.read_parquet(clusters_path)
    embeddings = np.load(str(embeddings_path))
    if embeddings.shape[0] != len(clusters_df):
        raise RuntimeError(
            f"Embedding matrix has {embeddings.shape[0]} rows but clusters parquet "
            f"has {len(clusters_df)} rows — row misalignment would corrupt centroids. "
            "Re-run `embed`/`cluster` so embeddings.npy matches clusters.parquet."
        )
    topic_info = (
        pd.read_parquet(topic_info_path)
        if topic_info_path and Path(topic_info_path).exists()
        else None
    )

    # 1. Corpus-base-rate normalization (ADR-045): the series fit AND display use.
    base_rate, base_rate_mean = corpus_base_rate(
        clusters_df, smoothing_window_days=smoothing
    )
    adj = adjusted_cluster_volumes(
        clusters_df,
        base_rate=base_rate,
        base_rate_mean=base_rate_mean,
        smoothing_window_days=smoothing,
    )

    all_ids = sorted(c for c in adj if c != NOISE_TOPIC)
    cluster_terms = {cid: _terms_from_topic_info(topic_info, cid)[1] for cid in all_ids}

    # 2. JEL scope (ADR-020 / ADR-046). Every non-noise cluster is analyzed; the
    # JEL label is a per-narrative flag, not a gate — out-of-scope clusters are
    # shown with their JEL code, not dropped from dynamics (ADR-046 reverses
    # ADR-020's "dropped from dynamics only").
    embedder = embedder if embedder is not None else _default_embedder()
    jel = classify_clusters(cluster_terms, embedder=embedder)
    fit_ids = list(all_ids)
    in_scope_n = sum(1 for cid in fit_ids if cid in jel and jel[cid].in_scope)
    log.info(
        "JEL scope: %d/%d non-noise clusters in-scope (E/F/G/H); all %d analyzed, "
        "out-of-scope flagged by JEL code (ADR-046)",
        in_scope_n, len(fit_ids), len(fit_ids),
    )
    if not fit_ids:
        raise RuntimeError(
            "No non-noise clusters to analyze — refusing to write an empty "
            "dashboard. Check clusters.parquet and topic_info."
        )

    # 3. Four-lens fit + stage on the adjusted series (ADR-039 / ADR-019).
    fitter = fitter if fitter is not None else DynamicsFitter(cfg)
    dynamics = {cid: fitter.fit_cluster(cid, adj[cid]) for cid in fit_ids}
    stages = {sc.cluster_id: sc for sc in classify_all(list(dynamics.values()), cfg)}

    # 4. Centroids → UMAP positions → similar narratives (ADR-044 / ADR-019 §H).
    centroids = _cluster_centroids(clusters_df, embeddings, fit_ids)
    umap_xy = _umap_positions(centroids, fit_ids, cfg)
    similar = compute_similar_narratives(
        fit_ids,
        centroids=centroids,
        top_terms={cid: cluster_terms[cid] for cid in fit_ids},
        volume_curves={cid: dynamics[cid].time_series for cid in fit_ids},
    )

    # 5. Assemble + persist (markets/mediacloud overlays absent — display follow-on).
    index, narratives = build_dashboard_artifacts(
        clusters_df=clusters_df,
        dynamics=dynamics,
        stages=stages,
        topic_info=topic_info,
        jel=jel,
        similar=similar,
        ordered_cluster_ids=fit_ids,
        centroids=centroids,
        umap_xy=umap_xy,
        cfg=cfg,
    )
    return write_dashboard_artifacts(index, narratives, out_dir)


def _default_embedder() -> Any:
    from mnd.embedding.embedder import Embedder

    return Embedder.from_config("primary")
