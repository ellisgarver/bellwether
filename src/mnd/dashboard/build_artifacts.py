"""Dashboard artifact builder — the pipeline→front-end seam (ADR-043).

This is the *only* place the heavy analysis outputs (fitted dynamics, JEL
assignments, embeddings, overlays) are baked into the small plain JSON the static
Astro site reads (ADR-043). The front end never imports bertopic/torch and
makes no API calls at view time — everything it needs is precomputed here.

The builder is deliberately a pure assembler: it does **not** run the lens
fits, FRED, or Media Cloud. It consumes already-computed pipeline objects
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
    SCHEMA_VERSION,
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
from mnd.dashboard.story_card import (
    NOISE_TOPIC,
    _terms_from_topic_info,
    build_story_card,
)
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
    peak_ci = (
        (_finite_or_none(fr.peak_time_ci_low), _finite_or_none(fr.peak_time_ci_high))
        if fr.peak_time_ci_low is not None and fr.peak_time_ci_high is not None
        else None
    )
    return FitArtifact(
        model=fr.model_name,
        converged=bool(fr.converged),
        aicc=_finite_or_none(fr.aicc),
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


def _median_article_words(clusters_df: pd.DataFrame) -> int | None:
    """Median word count per clustered article (non-noise), folding chunks → articles.

    Chunks of one document share an ``article_id``; the article's text is its chunk
    bodies joined, and its length is whitespace-token count. Returns ``None`` when
    there's no body column or no clustered article to count.
    """
    if "body" not in clusters_df.columns or "article_id" not in clusters_df.columns:
        return None
    rows = clusters_df[clusters_df["topic"] != NOISE_TOPIC]
    if rows.empty:
        return None
    bodies = rows.assign(_body=rows["body"].fillna("").astype(str))
    per_article = bodies.groupby("article_id")["_body"].apply(lambda s: len(" ".join(s).split()))
    if per_article.empty:
        return None
    return int(round(float(per_article.median())))


def _compute_emerging(
    date_range: tuple[str, str] | None, frontier: str | None, weeks: int
) -> bool:
    """Recency half of the emerging flag: onset within ``weeks`` of the corpus frontier.

    Reference point is the corpus frontier (the latest last-active date across all
    narratives), not wall-clock now, so a corpus built weeks ago still flags its own
    freshest narratives correctly. This is the whole emerging flag (ADR-059): a
    narrative is emerging iff its onset falls within the recency window, regardless
    of its trajectory stage.
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
    names: dict[int, "NarrativeName"] | None = None,
    cfg: dict[str, Any] | None = None,
    top_k_edges: int = 3,
    generated_at: str | None = None,
    n_clusters_total: int | None = None,
    corpus_jel: dict[int, str] | None = None,
    cards: dict[int, "StoryCard"] | None = None,
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
    names = names or {}
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

    # Reuse pre-built cards when the caller shares them (so naming and display
    # ground on the same central articles, ADR-061); else build them here.
    cards = cards or {cid: build_story_card(cid, clusters_df, topic_info) for cid in cluster_ids}

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
        nm = names.get(cid)

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
                label_human=nm.title if nm else None,
                description=nm.description if nm else None,
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
                label_human=nm.title if nm else None,
                stage=stage,
                n_articles=card.n_articles,
                top_terms=card.top_terms,
                peak_date=card.peak_date,
                date_range=card.date_range,
                in_scope=jel_obj.in_scope if jel_obj else True,
                jel_code=jel_obj.primary_code if jel_obj else None,
                # Emerging = just-arrived: onset within the recency window of the
                # corpus frontier, independent of stage (ADR-059). A narrative that
                # first appears in the trailing weeks is surfaced as emerging whether
                # or not its short history already registers a significant trend.
                is_emerging=_compute_emerging(card.date_range, frontier, recency_weeks),
                # Press-heating: the press is spiking on this tracked narrative now
                # (ADR-064). A separate signal from institutional recency, never merged.
                is_press_heating=bool(
                    (mc := mediacloud.get(cid)) is not None
                    and mc.press_heating
                    and mc.press_heating.get("is_heating")
                ),
                umap_xy=umap_xy.get(cid),
                umap_xyz=umap_xyz.get(cid),
                similar_edges=edges.get(cid, []),
            )
        )

    # Gallery order: in-scope macro narratives first, then largest within each
    # scope band. The educational default foregrounds the relevant macro stories
    # (JEL E/F/G/H); out-of-scope clusters stay in the index and are sorted lower,
    # not dropped (ADR-046 — JEL is a display flag, not a gate). True > False under
    # reverse, so in-scope leads; n_articles breaks ties largest-first as before.
    index_rows.sort(key=lambda e: (e.in_scope, e.n_articles), reverse=True)

    index = DashboardIndex(
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        global_random_seed=int(cfg["reproducibility"]["global_random_seed"]),
        n_narratives=len(index_rows),
        narratives=index_rows,
        median_article_words=_median_article_words(clusters_df),
        n_clusters_total=n_clusters_total,
        n_articles_corpus=(
            int(clusters_df["article_id"].nunique())
            if "article_id" in clusters_df.columns
            else None
        ),
        corpus_composition=_corpus_composition(clusters_df, corpus_jel),
        min_articles_to_fit=(
            int(cfg["dynamics"]["min_articles_to_fit"])
            if "min_articles_to_fit" in cfg.get("dynamics", {})
            else None
        ),
    )

    log.info(
        "Built dashboard artifacts: %d narratives, %d with semantic edges, "
        "%d emerging",
        len(narratives),
        sum(1 for e in index_rows if e.similar_edges),
        sum(1 for e in index_rows if e.is_emerging),
    )
    return index, narratives


def _corpus_composition(
    clusters_df: pd.DataFrame,
    corpus_jel: dict[int, str] | None,
) -> dict[str, dict[str, int]] | None:
    """Full-corpus article counts by source and by JEL code (ADR-076).

    Aggregates over every non-noise cluster — the whole corpus, not just the
    surfaced narratives — so the data page can chart the real composition. ``by_source``
    is distinct-article counts per ``source_id``; ``by_jel`` maps each cluster's
    distinct-article count onto its JEL code from ``corpus_jel`` (omitted when no
    full-corpus JEL was computed, so the front end falls back to surfaced JEL).
    Returns ``None`` when the frame lacks the needed columns (sample data).
    """
    if "article_id" not in clusters_df.columns:
        return None
    rows = (
        clusters_df[clusters_df["topic"] != NOISE_TOPIC]
        if "topic" in clusters_df.columns
        else clusters_df
    )
    if rows.empty:
        return None

    comp: dict[str, dict[str, int]] = {}
    if "source_id" in rows.columns:
        by_source = rows.groupby("source_id")["article_id"].nunique()
        comp["by_source"] = {str(k): int(v) for k, v in by_source.items()}
    if corpus_jel and "topic" in rows.columns:
        per_cluster = rows.groupby("topic")["article_id"].nunique()
        by_jel: dict[str, int] = {}
        for cid, n in per_cluster.items():
            code = corpus_jel.get(int(cid))
            if code:
                by_jel[code] = by_jel.get(code, 0) + int(n)
        if by_jel:
            comp["by_jel"] = by_jel
    return comp or None


def _corpus_heating(
    day_counts: pd.Series,
    frontier: str,
    *,
    recent_weeks: int,
    baseline_weeks: int,
    k: float,
    min_articles: int,
) -> dict[str, Any] | None:
    """Corpus-heating blob for one cluster (ADR-074).

    Fires when the cluster's mean weekly article count over the most-recent
    ``recent_weeks`` sits ``>= k`` standard errors above its own trailing
    ``baseline_weeks`` baseline, with at least ``min_articles`` in the recent
    window. Same shape as ``mnd.detection.mediacloud.press_heating`` (recent
    window vs. the narrative's own yearly baseline), but the z is scaled by
    ``sqrt(recent_weeks)``: institutional volume is single-digit weekly counts,
    so a windowed mean can never clear ``k`` raw weekly sigmas. Weeks with no
    articles count as zero (silence is signal). Returns ``None`` when there is
    too little history to judge.
    """
    if day_counts.empty:
        return None
    weekly = (
        day_counts.resample("W")
        .sum()
        .reindex(
            pd.date_range(day_counts.index.min(), pd.to_datetime(frontier), freq="W"),
            fill_value=0.0,
        )
    )
    if len(weekly) < recent_weeks + baseline_weeks:
        return None
    recent = weekly.iloc[-recent_weeks:]
    baseline = weekly.iloc[-(recent_weeks + baseline_weeks):-recent_weeks]
    base_std = float(baseline.std(ddof=1))
    if base_std <= 0.0:
        return None
    z = (float(recent.mean()) - float(baseline.mean())) / (
        base_std / math.sqrt(recent_weeks)
    )
    return {
        "is_heating": bool(z >= k and int(recent.sum()) >= min_articles),
        "z": round(z, 3),
        "recent_articles": int(recent.sum()),
        "recent_weeks": recent_weeks,
        "baseline_weeks": baseline_weeks,
        "k": k,
    }


def build_light_artifacts(
    light_ids: list[int],
    adj: dict[int, "pd.Series"],
    clusters_df: pd.DataFrame,
    topic_info: pd.DataFrame | None,
    corpus_jel: dict[int, str],
    centroids_by_cid: dict[int, Any],
    names: dict[int, Any],
    cfg: dict[str, Any],
    out_dir: str | Path,
) -> int:
    """Write one compact ``narrative_light_<id>.json`` per sub-floor cluster (ADR-083).

    The light tier: every non-noise cluster below the ADR-051 fit floor gets a
    page-sized artifact — name (patched in by the naming job), weekly volume
    series, model-free stage + shape facts, story card (references), JEL flag,
    corpus-heating blob, and semantic nearest neighbours. No lens fits, no
    press/market overlays, no lead-lag: those layers stay behind the
    identifiability floor. The volume ships on the WEEKLY grid (``freq="W"``)
    so ~7k artifacts stay deployable (daily grids are what make full artifacts
    ~570 KB each).
    """
    from dataclasses import asdict

    from mnd.dynamics.models import shape_facts as _shape_facts
    from mnd.stages.classify import classify_stage

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    smoothing = int(cfg["dynamics"]["smoothing_window_days"])
    heat_cfg = (cfg.get("display") or {}).get("corpus_heating") or {}
    scope_codes = {"E", "F", "G", "H"}

    # Corpus frontier across every cluster's series (same reference as staging).
    lasts = [s.index[-1] for s in adj.values() if len(s)]
    frontier = max(lasts) if lasts else None

    # Semantic neighbours across the FULL cluster set (surfaced + light), so a
    # light page can point at the related full narrative when one exists.
    all_ids = sorted(centroids_by_cid)
    sem_top: dict[int, list[int]] = {}
    if len(all_ids) > 1:
        mat = np.stack([np.asarray(centroids_by_cid[c], dtype=np.float32) for c in all_ids])
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat = mat / norms
        id_arr = np.asarray(all_ids)
        light_set = set(int(c) for c in light_ids)
        rows = [i for i, c in enumerate(all_ids) if int(c) in light_set]
        for start in range(0, len(rows), 512):
            block = rows[start:start + 512]
            sims = mat[block] @ mat.T
            for bi, i in enumerate(block):
                order = np.argsort(-sims[bi])
                nbrs = [int(id_arr[j]) for j in order if j != i][:5]
                sem_top[int(id_arr[i])] = nbrs

    # Distinct-article daily counts (raw) for the heating blob.
    rows = clusters_df[clusters_df["topic"] != NOISE_TOPIC]
    days = rows.assign(_d=rows["published_at"].astype(str).str.slice(0, 10))
    days = days[days["_d"].str.match(r"\d{4}-\d{2}-\d{2}")]
    arts = days.drop_duplicates(subset=["topic", "article_id"])

    n_written = 0
    for cid in light_ids:
        series = adj.get(cid)
        if series is None or not len(series):
            continue
        smoothed = series.rolling(smoothing, center=True, min_periods=1).mean()
        weekly = series.resample("W-MON", label="left").mean()
        weekly = weekly.round(4)

        stage_obj = classify_stage(cid, None, smoothed, cfg, frontier=frontier)
        t = np.arange(len(smoothed), dtype=float)
        facts = _shape_facts(t, smoothed.to_numpy(dtype=float))

        card = build_story_card(cid, clusters_df, topic_info)
        label = card.label

        heat = None
        grp = arts[arts["topic"] == cid]
        if frontier is not None and not grp.empty:
            per_day = grp.groupby("_d").size()
            counts = pd.Series(
                per_day.to_numpy(dtype=float), index=pd.to_datetime(per_day.index)
            ).sort_index()
            h = _corpus_heating(
                counts, frontier,
                recent_weeks=int(heat_cfg.get("recent_weeks", 16)),
                baseline_weeks=int(heat_cfg.get("baseline_weeks", 52)),
                k=float(heat_cfg.get("k_sigma", 2.0)),
                min_articles=int(heat_cfg.get("min_articles", 3)),
            )
            if h and h.get("is_heating"):
                heat = h

        nm = names.get(cid)
        jel_code = corpus_jel.get(int(cid))
        payload = {
            "schema_version": SCHEMA_VERSION,
            "tier": "light",
            "cluster_id": int(cid),
            "label": label,
            "label_human": getattr(nm, "title", None),
            "description": getattr(nm, "description", None),
            "stage": stage_obj.stage,
            "stage_detail": _json_safe(stage_obj.detail),
            "shape_facts": {k: float(v) for k, v in facts.items()},
            "volume": asdict(_series_artifact(weekly, freq="W")),
            "card": card.to_dict(),
            "jel": (
                {"code": jel_code, "in_scope": jel_code[0] in scope_codes}
                if jel_code else None
            ),
            "similar": {"semantic": sem_top.get(int(cid), []),
                        "lexical": [], "morphological": []},
            "heating": heat,
            "fits": [],
            "mediacloud": None,
            "markets": None,
        }
        (out / f"narrative_light_{int(cid)}.json").write_text(
            json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False)
        )
        n_written += 1
    log.info("Wrote %d light-tier narrative artifacts to %s", n_written, out)
    return n_written


def write_cluster_directory(
    clusters_df: pd.DataFrame,
    topic_info: pd.DataFrame | None,
    fit_ids: list[int],
    names: dict[int, Any],
    out_dir: str | Path,
    cfg: dict[str, Any] | None = None,
) -> Path | None:
    """Write ``clusters_all.json`` — the full-corpus cluster directory.

    One compact row per non-noise cluster (all of them, not just the surfaced
    narratives): id, c-TF-IDF label, display name when one exists, article count,
    date span, and whether the cluster has a narrative page. Lets the site offer
    a searchable directory of the entire corpus without baking 7,000+ full
    artifacts.

    Every non-surfaced entry carries its c-TF-IDF ``terms`` so the naming layer
    can title the whole directory from terms alone (ADR-073); surfaced clusters
    are titled from their full story cards and need no directory terms.
    Sub-floor clusters whose onset falls within the ADR-059 recency window and
    which span at least ``display.forming.min_articles`` distinct articles are
    additionally flagged ``forming`` (ADR-071) for the emerging page. Sub-floor
    clusters whose recent volume spikes against their own baseline additionally
    carry a ``heating`` blob (ADR-074) — their weekly series never ships, so the
    signal must be baked here; the site computes the same signal for surfaced
    narratives from their shipped series. Returns the written path, or ``None``
    when the frame lacks the needed columns (sample/partial data).
    """
    if "topic" not in clusters_df.columns or "article_id" not in clusters_df.columns:
        return None
    rows = clusters_df[clusters_df["topic"] != NOISE_TOPIC]
    if rows.empty:
        return None
    cfg = cfg or load_config()

    counts = rows.groupby("topic")["article_id"].nunique()
    date_ranges: dict[int, tuple[str, str]] = {}
    day_counts: dict[int, pd.Series] = {}
    if "published_at" in rows.columns:
        days = rows.assign(_d=rows["published_at"].astype(str).str.slice(0, 10))
        days = days[days["_d"].str.match(r"\d{4}-\d{2}-\d{2}")]
        if not days.empty:
            g = days.groupby("topic")["_d"]
            date_ranges = {
                int(cid): (str(lo), str(hi))
                for cid, lo, hi in zip(g.min().index, g.min(), g.max())
            }
            # Distinct-article daily counts per cluster, for the heating signal.
            arts = days.drop_duplicates(subset=["topic", "article_id"])
            for cid, grp in arts.groupby("topic"):
                per_day = grp.groupby("_d").size()
                day_counts[int(cid)] = pd.Series(
                    per_day.to_numpy(dtype=float), index=pd.to_datetime(per_day.index)
                ).sort_index()

    # Forming window (ADR-071): onset within display.forming.recency_weeks of
    # the corpus frontier (independent of the surfaced emerging window).
    forming_cfg = (cfg.get("display") or {}).get("forming") or {}
    recency_weeks = int(forming_cfg.get("recency_weeks", 4))
    forming_floor = int(forming_cfg.get("min_articles", 3))
    frontier = max((hi for _, hi in date_ranges.values()), default=None)
    forming_cut = (
        (pd.to_datetime(frontier) - pd.Timedelta(weeks=recency_weeks)).date().isoformat()
        if frontier
        else None
    )
    heat_cfg = (cfg.get("display") or {}).get("corpus_heating") or {}

    surfaced = {int(c) for c in fit_ids}
    entries = []
    for cid in sorted(int(c) for c in counts.index):
        nm = names.get(cid)
        n_articles = int(counts[cid])
        dr = date_ranges.get(cid)
        forming = bool(
            forming_cut
            and cid not in surfaced
            and dr is not None
            and dr[0] >= forming_cut
            and n_articles >= forming_floor
        )
        entry = {
            "cluster_id": cid,
            "label": _terms_from_topic_info(topic_info, cid)[0],
            "label_human": getattr(nm, "title", None),
            "n_articles": n_articles,
            "date_range": list(dr) if dr else None,
            "surfaced": cid in surfaced,
            "forming": forming,
        }
        if cid not in surfaced:
            entry["terms"] = _terms_from_topic_info(topic_info, cid)[1]
            # Heating blob only where it fires — one compact row per cluster.
            if frontier and cid in day_counts:
                heat = _corpus_heating(
                    day_counts[cid],
                    frontier,
                    recent_weeks=int(heat_cfg.get("recent_weeks", 16)),
                    baseline_weeks=int(heat_cfg.get("baseline_weeks", 52)),
                    k=float(heat_cfg.get("k_sigma", 2.0)),
                    min_articles=int(heat_cfg.get("min_articles", 3)),
                )
                if heat and heat["is_heating"]:
                    entry["heating"] = heat
        entries.append(entry)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "clusters_all.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "n_clusters": len(entries),
                "clusters": entries,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    log.info("Wrote full-corpus cluster directory (%d clusters) to %s", len(entries), path)
    return path


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
