"""Dashboard artifact builder — the pipeline→front-end seam (ADR-043).

This is the *only* place the heavy analysis outputs (fitted dynamics, JEL
assignments, embeddings, overlays) are baked into the small plain JSON the static
Astro site reads (ADR-043). The front end never imports pymc/bertopic/torch and
makes no API calls at view time — everything it needs is precomputed here.

The builder is deliberately a pure assembler: it does **not** run PyMC, FRED, or
Media Cloud. It consumes already-computed pipeline objects
(``ClusterDynamics``, ``StageClassification``, ``ClusterJELAssignment``, the
``MarketsArtifact`` / ``MediaCloudArtifact`` overlays) plus the cluster frame, and
emits the ``DashboardIndex`` + per-narrative ``NarrativeArtifact`` objects defined
in ``artifacts.py``. That keeps it cheap, deterministic, and unit-testable with
synthetic inputs.

Two things are derived here rather than received:

* **Story cards** — extractive, cheap, deterministic (``story_card.build_story_card``).
* **The map's semantic edges** — top-k cosine neighbors with weights, from the
  cluster centroids (ADR-044). ``umap_xy`` positions are passed through.

The narrative-page **similar-narratives panel** (all three ADR-019 §H measures) is
*received*, not derived: pass ``compute_similar_narratives(...)`` output as
``similar``. That keeps the builder a pure assembler and avoids recomputing the
lexical/morphological measures it has no inputs for. The map's semantic edges and
the panel's semantic list use the same measure but different ``top_k`` (3 for graph
legibility, 5 for the panel) — intentional, not a bug.

"Curves not parameters" (ADR-039): each ``FitResult`` already carries its display
``curve`` evaluated on the daily grid; we copy it straight across so the front end
plots curve-vs-observed without touching parameters.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mnd.clustering.jel_classifier import ClusterJELAssignment
from mnd.clustering.similar_narratives import semantic_similarity_weighted
from mnd.dashboard.artifacts import (
    DashboardIndex,
    FitArtifact,
    IndexEntry,
    JELArtifact,
    MediaCloudArtifact,
    MarketsArtifact,
    NarrativeArtifact,
    SeriesArtifact,
    SimilarNarratives,
)
from mnd.dashboard.story_card import NOISE_TOPIC, build_story_card
from mnd.dynamics.fitting import ClusterDynamics, FitResult
from mnd.stages.classify import StageClassification
from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Small numeric/JSON helpers
# ---------------------------------------------------------------------------


def _finite_or_none(x: Any) -> float | None:
    """Coerce a value to a JSON-safe float, mapping inf/nan/None → None."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _json_safe(obj: Any) -> Any:
    """Recursively replace non-finite floats with None so json.dump never emits NaN."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


# ---------------------------------------------------------------------------
# Per-piece converters
# ---------------------------------------------------------------------------


def _series_artifact(series: pd.Series, freq: str = "D") -> SeriesArtifact:
    s = series.dropna()
    idx = pd.to_datetime(s.index)
    return SeriesArtifact(
        dates=[d.strftime("%Y-%m-%d") for d in idx],
        values=[float(v) for v in s.to_numpy(dtype=float)],
        freq=freq,
    )


def _fit_artifact(fr: FitResult) -> FitArtifact:
    r0_ci = (
        (_finite_or_none(fr.r0_ci_low), _finite_or_none(fr.r0_ci_high))
        if fr.r0_ci_low is not None and fr.r0_ci_high is not None
        else None
    )
    peak_ci = (
        (_finite_or_none(fr.peak_time_ci_low), _finite_or_none(fr.peak_time_ci_high))
        if fr.peak_time_ci_low is not None and fr.peak_time_ci_high is not None
        else None
    )
    return FitArtifact(
        model=fr.model_name,
        converged=bool(fr.converged),
        aicc=_finite_or_none(fr.aicc),
        r0_mean=_finite_or_none(fr.r0_mean),
        r0_ci=r0_ci,
        peak_time_mean=_finite_or_none(fr.peak_time_mean),
        peak_time_ci=peak_ci,
        params=_json_safe(fr.param_summary),
        curve=fr.curve,
        failure_reason=fr.failure_reason,
    )


def _jel_artifact(a: ClusterJELAssignment) -> JELArtifact:
    return JELArtifact(
        code=a.primary_code,
        in_scope=bool(a.in_scope),
        similarity=float(a.similarity),
        runner_up=a.runner_up,
        runner_up_gap=float(a.runner_up_gap),
    )


def _similar_artifact(d: dict[str, list[Any]]) -> SimilarNarratives:
    """Map a compute_similar_narratives entry → SimilarNarratives (ADR-019 §H)."""
    return SimilarNarratives(
        semantic=[int(x) for x in d.get("semantic", [])],
        lexical=[int(x) for x in d.get("lexical", [])],
        morphological=[int(x) for x in d.get("morphological", [])],
    )


def _compute_emerging(
    date_range: tuple[str, str] | None, frontier: str | None, weeks: int
) -> bool:
    """Newly-emerging = the narrative's onset is within ``weeks`` of the corpus frontier.

    Reference point is the corpus frontier (the latest last-active date across all
    narratives), not wall-clock now, so a corpus built weeks ago still flags its own
    freshest narratives correctly (ADR-019 recency filter, not a stage).
    """
    if not date_range or not frontier:
        return False
    onset = pd.to_datetime(date_range[0])
    ref = pd.to_datetime(frontier)
    return (ref - onset) <= pd.Timedelta(weeks=weeks)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_dashboard_artifacts(
    *,
    clusters_df: pd.DataFrame,
    dynamics: dict[int, ClusterDynamics],
    stages: dict[int, StageClassification],
    topic_info: pd.DataFrame | None = None,
    jel: dict[int, ClusterJELAssignment] | None = None,
    similar: dict[int, dict[str, list[int]]] | None = None,
    ordered_cluster_ids: list[int] | None = None,
    centroids: np.ndarray | None = None,
    umap_xy: dict[int, tuple[float, float]] | None = None,
    umap_xyz: dict[int, tuple[float, float, float]] | None = None,
    markets: dict[int, MarketsArtifact] | None = None,
    mediacloud: dict[int, MediaCloudArtifact] | None = None,
    cfg: dict[str, Any] | None = None,
    top_k_edges: int = 3,
    generated_at: str | None = None,
) -> tuple[DashboardIndex, list[NarrativeArtifact]]:
    """Assemble the dashboard index + per-narrative artifacts.

    Emits one artifact per non-noise cluster present in ``dynamics``. Story cards
    and the map's semantic edges are derived here; everything else is passed
    through from the precomputed pipeline objects. Returns the objects (no I/O);
    use ``write_dashboard_artifacts`` to persist.
    """
    cfg = cfg or load_config()
    jel = jel or {}
    similar = similar or {}
    umap_xy = umap_xy or {}
    umap_xyz = umap_xyz or {}
    markets = markets or {}
    mediacloud = mediacloud or {}
    recency_weeks = int(cfg["stages"]["newly_emerging_recency_weeks"])

    cluster_ids = sorted(c for c in dynamics if int(c) != NOISE_TOPIC)

    # Semantic edges for the narrative map (ADR-044). Weighted top-k cosine on
    # centroids; only computed when centroids + their id order are supplied.
    edges: dict[int, list[tuple[int, float]]] = {}
    if centroids is not None and ordered_cluster_ids is not None:
        weighted = semantic_similarity_weighted(
            ordered_cluster_ids, centroids, top_k=top_k_edges
        )
        edges = {
            int(cid): [(int(n), float(w)) for n, w in nbrs]
            for cid, nbrs in weighted.items()
        }

    cards = {cid: build_story_card(cid, clusters_df, topic_info) for cid in cluster_ids}

    # Corpus frontier = latest last-active date across narratives (emerging ref).
    last_dates = [c.date_range[1] for c in cards.values() if c.date_range]
    frontier = max(last_dates) if last_dates else None

    narratives: list[NarrativeArtifact] = []
    index_rows: list[IndexEntry] = []

    for cid in cluster_ids:
        cd = dynamics[cid]
        card = cards[cid]
        stage_obj = stages.get(cid)
        stage = stage_obj.stage if stage_obj else "dormant"
        stage_detail = stage_obj.detail if stage_obj else {}
        jel_obj = jel.get(cid)

        observed = cd.raw_series if cd.raw_series is not None else cd.time_series
        volume = (
            _series_artifact(observed)
            if observed is not None
            else SeriesArtifact(dates=[], values=[])
        )

        narratives.append(
            NarrativeArtifact(
                cluster_id=int(cid),
                label=card.label,
                stage=stage,
                card=card.to_dict(),
                volume=volume,
                fits=[_fit_artifact(fr) for fr in cd.all_fits],
                staging_model=cd.staging_fit.model_name,
                shape_facts={k: float(v) for k, v in cd.shape_facts.items()},
                stage_detail=_json_safe(stage_detail),
                jel=_jel_artifact(jel_obj) if jel_obj else None,
                similar=_similar_artifact(similar[cid]) if cid in similar else None,
                mediacloud=mediacloud.get(cid),
                markets=markets.get(cid),
            )
        )

        index_rows.append(
            IndexEntry(
                cluster_id=int(cid),
                label=card.label,
                stage=stage,
                n_articles=card.n_articles,
                top_terms=card.top_terms,
                peak_date=card.peak_date,
                date_range=card.date_range,
                in_scope=jel_obj.in_scope if jel_obj else True,
                jel_code=jel_obj.primary_code if jel_obj else None,
                is_emerging=_compute_emerging(card.date_range, frontier, recency_weeks),
                umap_xy=umap_xy.get(cid),
                umap_xyz=umap_xyz.get(cid),
                similar_edges=edges.get(cid, []),
            )
        )

    # Gallery order: largest narrative first (matches story-card convention).
    index_rows.sort(key=lambda e: e.n_articles, reverse=True)

    index = DashboardIndex(
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        global_random_seed=int(cfg["reproducibility"]["global_random_seed"]),
        stage_min_r0=float(cfg["stages"]["growth_min_r0"]),
        n_narratives=len(index_rows),
        narratives=index_rows,
    )

    log.info(
        "Built dashboard artifacts: %d narratives, %d with semantic edges, "
        "%d emerging",
        len(narratives),
        sum(1 for e in index_rows if e.similar_edges),
        sum(1 for e in index_rows if e.is_emerging),
    )
    return index, narratives


def write_dashboard_artifacts(
    index: DashboardIndex,
    narratives: list[NarrativeArtifact],
    out_dir: str | Path,
) -> Path:
    """Write ``index.json`` + one ``narrative_<id>.json`` per narrative to ``out_dir``.

    Returns the output directory. Non-finite floats are scrubbed to ``null`` so the
    JSON is strictly valid (no ``NaN``/``Infinity`` tokens a browser would reject).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "index.json").write_text(
        json.dumps(_json_safe(index.to_dict()), indent=2, allow_nan=False)
    )
    for art in narratives:
        (out / art.filename()).write_text(
            json.dumps(_json_safe(art.to_dict()), indent=2, allow_nan=False)
        )

    log.info("Wrote %d narrative artifacts + index to %s", len(narratives), out)
    return out
