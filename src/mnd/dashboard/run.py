"""Downstream analysis driver: clusters.parquet → dashboard artifacts.

``cluster`` persists ``clusters.parquet`` (+ ``topic_info.parquet``) and
``embeddings.npy``; the front end reads the small JSON in
``paths.dashboard_artifacts``. ``run_analysis`` connects the two — it recomputes
the entire analysis layer from the persisted clustering, with no re-embedding
(the embed+cluster step is the only irreversible one-shot work).

Pipeline assembled here, in order:

  1. corpus-base-rate normalization of per-cluster daily volume (ADR-045) — the
     series both the fit and the dashboard use, so corpus growth does not
     confound either.
  2. JEL scope classification of each cluster (ADR-020); the JEL code is a
     per-narrative flag, not a gate — every non-noise cluster is carried into
     dynamics and out-of-scope ones (JEL ∉ {E,F,G,H}) are shown flagged with
     their code, not dropped (ADR-046).
  3. per-cluster lens fits (least squares, ADR-067) on the adjusted series,
     and model-free stage classification from the volume trajectory (ADR-052).
  4. cluster centroids + 2-D UMAP positions + semantic/lexical/morphological
     similar-narratives (ADR-019 §H, ADR-044).
  5. assembly into the artifact contract via ``build_dashboard_artifacts`` and
     persistence via ``write_dashboard_artifacts``.

Two display overlays are built here, each keyed on its own credential and each
degrading to absent (the front end omits the section) when its key is missing:
the markets/Granger overlay (ADR-041/047) against the canonical VIX series with a
FRED key, and the Media Cloud broad-press story-count overlay with a bidirectional
press-vs-discourse Granger readout (ADR-042/048) with a MEDIACLOUD key. Both are
display/validation only — neither ever feeds embedding, clustering, or the fit.

``embedder`` and ``fitter`` are injectable so the assembly path is unit-testable
without loading Qwen3-8B or running the lens fits; the CLI passes the real ones.
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
    write_cluster_directory,
    write_dashboard_artifacts,
)
from mnd.dashboard.naming import NamingInput, generate_names
from mnd.dashboard.story_card import (
    NOISE_TOPIC,
    _terms_from_topic_info,
    build_story_card,
)
from mnd.dynamics.fitting import ClusterDynamics, DynamicsFitter
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
    centroids: np.ndarray,
    ordered_ids: list[int],
    cfg: dict[str, Any],
    n_components: int = 3,
) -> dict[int, tuple[float, ...]]:
    """UMAP of the cluster centroids for the narrative map (ADR-044).

    Mirrors the clustering UMAP params (cosine, min_dist) but at the requested
    ``n_components`` and seeded from the global seed for reproducibility. The home
    map renders in 3-D, so the default is 3 components (the front end derives the
    2-D position from the first two). ``n_neighbors`` is clamped below the cluster
    count (UMAP requires n_neighbors < n_samples); with too few clusters for a
    meaningful embedding we fall back to a deterministic line.
    """
    n = len(ordered_ids)
    if n <= n_components:
        return {
            cid: (float(i),) + (0.0,) * (n_components - 1)
            for i, cid in enumerate(ordered_ids)
        }
    from umap import UMAP

    uc = cfg["clustering"]["umap"]
    seed = int(cfg["reproducibility"]["global_random_seed"])
    reducer = UMAP(
        n_components=n_components,
        n_neighbors=min(int(uc["n_neighbors"]), n - 1),
        min_dist=float(uc["min_dist"]),
        metric=uc["metric"],
        random_state=seed,
    )
    coords = reducer.fit_transform(centroids)
    return {
        cid: tuple(float(v) for v in coords[i]) for i, cid in enumerate(ordered_ids)
    }


def _fit_with_resume(
    fitter: DynamicsFitter,
    series_by_cid: dict[int, pd.Series],
    cfg: dict[str, Any],
    cache_dir: Path,
) -> dict[int, ClusterDynamics]:
    """Fit every cluster, caching each lens so a re-run resumes and reuses (ADR-065).

    Caching is now per-(cluster, lens): ``fit_cluster`` reloads any lens whose own
    config is unchanged and fits only the rest, so a one-lens prior change re-fits
    only that lens (not all three), and a wall-clock timeout loses at most one lens
    of one cluster. Staging + shape-facts are recomputed (cheap, model-free).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    fitter._cache_loaded = 0
    fitter._cache_fit = 0
    out: dict[int, ClusterDynamics] = {
        cid: fitter.fit_cluster(cid, series, cache_dir=cache_dir)
        for cid, series in series_by_cid.items()
    }
    log.info(
        "Dynamics fits: %d lens-fits loaded from cache, %d freshly fit "
        "(per-lens, ADR-065; cache dir: %s)",
        fitter._cache_loaded, fitter._cache_fit, cache_dir,
    )
    return out


def run_analysis(
    *,
    clusters_path: str | Path,
    embeddings_path: str | Path,
    out_dir: str | Path,
    topic_info_path: str | Path | None = None,
    cfg: dict[str, Any] | None = None,
    embedder: Any | None = None,
    fitter: DynamicsFitter | None = None,
    namer: Any | None = None,
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
    # 2. Fit/display floor (ADR-051) + JEL scope flag (ADR-046).
    # BERTopic at the library-default min_cluster_size (ADR-019) yields thousands
    # of micro-topics (median ~7 articles): too few points to identify a
    # 3-parameter lifecycle curve, and far too many to navigate. Only clusters
    # with >= dynamics.min_articles_to_fit unique articles are fit, staged, and
    # surfaced (map/narratives/emerging/search); the rest stay in clusters.parquet
    # and are reported as an aggregate count (n_clusters_total) but get no
    # dynamics, map point, or search entry. Clustering is untouched — the floor is
    # a post-clustering display/analysis selection, not a tuned hyperparameter
    # (ADR-040 holds; fixed a priori, never adjusted to improve anchor recovery).
    floor = int(cfg["dynamics"]["min_articles_to_fit"])
    article_counts = (
        clusters_df.loc[clusters_df["topic"] != NOISE_TOPIC]
        .groupby("topic")["article_id"]
        .nunique()
    )
    fit_ids = [cid for cid in all_ids if int(article_counts.get(cid, 0)) >= floor]
    log.info(
        "Fit/display floor (ADR-051): %d of %d non-noise clusters have >=%d "
        "articles — fitting + surfacing those; %d sub-threshold clusters retained "
        "in clusters.parquet but not surfaced.",
        len(fit_ids), len(all_ids), floor, len(all_ids) - len(fit_ids),
    )
    if not fit_ids:
        raise RuntimeError(
            f"No clusters have >= {floor} articles — refusing to write an empty "
            "dashboard. Lower dynamics.min_articles_to_fit or check clusters.parquet."
        )

    # Cluster centroids (mean chunk embedding) — reused for JEL scope, the UMAP map,
    # and similar-narratives, so we embed nothing per cluster (ADR-067).
    centroids = _cluster_centroids(clusters_df, embeddings, fit_ids)
    centroid_by_cid = {cid: centroids[i] for i, cid in enumerate(fit_ids)}
    cluster_terms = {cid: _terms_from_topic_info(topic_info, cid)[1] for cid in fit_ids}

    # JEL scope is a per-narrative display flag, not a gate (ADR-046): out-of-scope
    # narratives are shown with their code, not dropped. Nearest-prototype on the
    # existing centroids (ADR-067) — no 8B re-encode; the embedder loads only if the
    # fixed JEL prototype vectors aren't cached yet.
    jel = _jel_scope(centroid_by_cid, cfg, Path(out_dir) / ".jel_cache", embedder=embedder)

    # Story cards (extractive) built once here and shared with naming + artifacts,
    # so the panels the reader sees and the excerpts the namer titles from are the
    # same central articles (ADR-061).
    cards = {cid: build_story_card(cid, clusters_df, topic_info) for cid in fit_ids}

    # 2b. Human-readable display names (ADR-056): a short LLM title + description
    # grounded on the cluster's central representative articles (ADR-061) plus its
    # date span and source mix. Display-only — never feeds the fit or scope —
    # cached/committed for deterministic, key-free rebuilds, and absent (front end
    # falls back to the c-TF-IDF label) when disabled or unkeyed.
    naming_inputs = _naming_inputs(fit_ids, cluster_terms, cards, clusters_df)
    names = generate_names(naming_inputs, cfg, client=namer)

    # 3. Four-lens fit + stage on the adjusted series (ADR-039 / ADR-019). Fits
    # are checkpointed per cluster under out_dir so a re-run resumes mid-corpus
    # rather than refitting from scratch after a wall-clock timeout.
    fitter = fitter if fitter is not None else DynamicsFitter(cfg)
    dynamics = _fit_with_resume(
        fitter, {cid: adj[cid] for cid in fit_ids}, cfg, Path(out_dir) / ".fit_cache"
    )
    stages = {sc.cluster_id: sc for sc in classify_all(list(dynamics.values()), cfg)}

    # 4. UMAP positions → similar narratives (ADR-044 / ADR-019 §H), from the
    # centroids computed above. The home map is 3-D; 2-D is its first two components.
    umap_xyz = _umap_positions(centroids, fit_ids, cfg, n_components=3)
    umap_xy = {cid: xyz[:2] for cid, xyz in umap_xyz.items()}
    similar = compute_similar_narratives(
        fit_ids,
        centroids=centroids,
        top_terms={cid: cluster_terms[cid] for cid in fit_ids},
        volume_curves={cid: dynamics[cid].time_series for cid in fit_ids},
    )

    # 5. Display overlays (ADR-041/047 markets, ADR-042/048 press) — each built per
    # narrative when its key is configured, absent otherwise (the front end omits
    # the section). Delta-cached + fetched efficiently (ADR-068); display-only.
    overlay_cache = Path(out_dir) / ".overlay_cache"
    markets = _markets_overlays(adj, fit_ids, cfg, overlay_cache)
    mediacloud = _mediacloud_overlays(adj, fit_ids, cluster_terms, cfg, overlay_cache)

    # 6. Assemble + persist.
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
        umap_xyz=umap_xyz,
        markets=markets,
        mediacloud=mediacloud,
        names=names,
        n_clusters_total=len(all_ids),
        cfg=cfg,
        cards=cards,
    )
    out_path = write_dashboard_artifacts(index, narratives, out_dir)
    # Full-corpus directory (every non-noise cluster, incl. sub-floor ones) so
    # the site can offer a searchable index of the whole corpus.
    write_cluster_directory(clusters_df, topic_info, fit_ids, names, out_dir)
    return out_path


def _naming_inputs(
    fit_ids: list[int],
    cluster_terms: dict[int, list[str]],
    cards: dict[int, Any],
    clusters_df: pd.DataFrame,
) -> list[NamingInput]:
    """Build the per-cluster representation the namer titles from (ADR-056/061).

    The excerpts are the cluster's *central* representative articles — the same
    most-aligned, most-substantial pieces surfaced on the narrative page (ADR-061) —
    so titles reflect what the reader sees. Terms, date span, and top sources add
    light grounding context. No model call here; this only assembles the inputs.
    """
    inputs: list[NamingInput] = []
    for cid in fit_ids:
        card = cards[cid]
        excerpts = [a["excerpt"] for a in card.central_articles if a.get("excerpt")]
        date_range = card.date_range
        sources = [s for s, _ in card.source_mix[:4]]
        inputs.append(
            NamingInput(
                cluster_id=int(cid),
                terms=cluster_terms[cid],
                excerpts=excerpts,
                date_range=date_range,
                sources=sources,
            )
        )
    return inputs


def _markets_overlays(
    adj: dict[int, pd.Series], fit_ids: list[int], cfg: dict[str, Any], cache_dir: Path,
) -> dict[int, Any]:
    """Build a VIX markets overlay + bidirectional Granger per narrative (ADR-047).

    VIX is the canonical series and the only one the lag test runs against. It is
    fetched from FRED **once** over the whole corpus span (delta-cached, ADR-068) and
    sliced per narrative — not re-fetched 365×. Requires a FRED key — if one is
    absent (or the fetch fails), narratives get no markets block and the front end
    omits the section. Short narratives (< 20 usable weekly obs) still get the overlay
    drawn; their Granger readout reports "insufficient data".
    """
    from mnd.detection.markets import TIMING_NOT_CAUSE, MarketsOverlay
    from mnd.detection.series_cache import cache_key, delta_fetch
    from mnd.dashboard.artifacts import MarketsArtifact

    try:
        overlay = MarketsOverlay.from_env()
    except Exception as exc:
        log.warning("Markets overlay skipped — no FRED client (%s); section absent", exc)
        return {}

    # Fetch the (single) VIX series once, delta-cached, over the global span.
    series_id = overlay._resolve_series_id("vix")
    starts = [adj[cid].index.min() for cid in fit_ids if len(adj[cid])]
    if not starts:
        return {}
    global_start = min(starts).date().isoformat()
    today = pd.Timestamp.utcnow().date().isoformat()
    refetch_days = int(cfg.get("detection", {}).get("markets", {}).get("refetch_days", 7))

    def _fred_fetch(a: str, b: str) -> list[dict]:
        raw = overlay._fred.fetch(series={series_id: series_id}, start=a, end=b)
        if raw is None or raw.empty or series_id not in raw.columns:
            return []
        return [
            {"date": pd.Timestamp(idx).date().isoformat(), "value": float(v)}
            for idx, v in raw[series_id].items() if pd.notna(v)
        ]

    try:
        records = delta_fetch(
            _fred_fetch, cache_dir / f"markets_{cache_key(series_id)}.json",
            global_start, today, refetch_days=refetch_days, today=today, date_key="date",
        )
    except Exception as exc:
        log.warning("Markets overlay skipped — FRED fetch failed (%s); section absent", exc)
        return {}
    if not records:
        return {}
    market_daily = pd.Series(
        {pd.Timestamp(r["date"]): r["value"] for r in records}
    ).sort_index()
    market_weekly = market_daily.resample("W").mean()

    out: dict[int, Any] = {}
    for cid in fit_ids:
        try:
            df = overlay.build_overlay(adj[cid], series="vix", market_weekly=market_weekly)
        except Exception as exc:
            log.warning("Markets overlay failed for cluster %d: %s", cid, exc)
            continue
        if df.empty or not df["market"].notna().any():
            continue
        series_id = df.attrs.get("series_id") or "VIXCLS"
        series_label = df.attrs.get("series_label") or "vix"
        df = df.dropna(subset=["volume", "market"])
        granger = overlay.granger_bidirectional(df)
        idx = pd.to_datetime(df.index)
        out[cid] = MarketsArtifact(
            series_id=series_id,
            series_label=series_label,
            dates=[d.date().isoformat() for d in idx],
            volume=[float(v) for v in df["volume"]],
            market=[float(m) for m in df["market"]],
            granger=granger,
            caption=TIMING_NOT_CAUSE,
        )
    log.info("Built VIX markets overlay for %d/%d narratives (ADR-047)", len(out), len(fit_ids))
    return out


def _mediacloud_query(terms: list[str], k: int) -> str:
    """OR the top-k cluster c-TF-IDF terms into a Media Cloud keyword query.

    Data-driven (the query is the cluster's own keywords, not a hand-written
    string) so the no-tuning rule holds. Multi-word terms are phrase-quoted.
    """
    parts = []
    for t in terms[:k]:
        t = t.strip()
        if not t:
            continue
        parts.append(f'"{t}"' if " " in t else t)
    return " OR ".join(parts)


def _press_granger(daily_volume: pd.Series, records: list[dict]) -> dict[str, Any] | None:
    """Weekly bidirectional Granger between discourse volume and press counts
    (ADR-048). Press counts occupy the generic ``market`` slot; ``other_label=
    "press"`` only sets the verdict wording. Returns None when there are no
    overlapping weekly observations."""
    from mnd.detection.markets import MarketsOverlay

    press = pd.Series(
        {pd.Timestamp(r["date"]): int(r["story_count"]) for r in records}
    ).sort_index()
    if press.empty:
        return None
    weekly_vol = MarketsOverlay.weekly_volume(daily_volume)
    weekly_press = press.resample("W").sum()
    weekly_press.name = "market"
    df = pd.concat([weekly_vol, weekly_press], axis=1).dropna()
    if df.empty:
        return None
    df.attrs["series_id"] = "mediacloud_us_national"
    df.attrs["series_label"] = "press"
    return MarketsOverlay(fred=None).granger_bidirectional(df, other_label="press")


def _mediacloud_overlays(
    adj: dict[int, pd.Series],
    fit_ids: list[int],
    cluster_terms: dict[int, list[str]],
    cfg: dict[str, Any],
    cache_dir: Path,
) -> dict[int, Any]:
    """Broad-press story-count overlay + bidirectional press-vs-discourse Granger
    per narrative (ADR-042/048). The per-narrative query is the OR of its top
    c-TF-IDF terms, delta-cached and fetched in parallel (ADR-068). Requires
    MEDIACLOUD_API_KEY — if absent (or a fetch fails), the affected narratives simply
    get no mediacloud block and the front end omits the section. Press coverage thins
    before ~2017; the artifact carries
    ``reliable_since_year`` so the UI can caption that rather than show a flat line.
    Display/validation only — never feeds embedding, clustering, or the fit.
    """
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date as _date

    from mnd.detection.mediacloud import (
        MediaCloudDetector,
        RELIABLE_SINCE_YEAR,
        press_heating,
    )
    from mnd.detection.series_cache import cache_key, delta_fetch
    from mnd.dashboard.artifacts import MediaCloudArtifact

    try:
        detector = MediaCloudDetector.from_env()
    except Exception as exc:
        log.warning("Media Cloud overlay skipped — no MEDIACLOUD key (%s); section absent", exc)
        return {}

    mc_cfg = cfg.get("detection", {}).get("mediacloud", {})
    k = int(mc_cfg.get("query_top_terms", 6))
    heat_cfg = mc_cfg.get("press_heating", {})
    refetch_days = int(mc_cfg.get("refetch_days", 28))
    max_workers = int(mc_cfg.get("max_workers", 6))
    caption = f"Broad-press story counts (Media Cloud). Reliable from ~{RELIABLE_SINCE_YEAR}."
    today = pd.Timestamp.utcnow().date().isoformat()

    # Per-narrative query + span; skip degenerate ones.
    tasks: list[tuple[int, str, str, str]] = []
    for cid in fit_ids:
        query = _mediacloud_query(cluster_terms.get(cid, []), k)
        idx = pd.to_datetime(adj[cid].index)
        if not query or len(idx) == 0:
            continue
        tasks.append((cid, query, idx.min().date().isoformat(), idx.max().date().isoformat()))

    def _fetch(task: tuple[int, str, str, str]) -> tuple[int, list[dict]]:
        cid, query, start, end = task
        fn = lambda a, b: list(  # noqa: E731
            detector.fetch_story_counts(query, _date.fromisoformat(a), _date.fromisoformat(b))
        )
        try:
            recs = delta_fetch(
                fn, cache_dir / f"mediacloud_{cache_key(query)}.json",
                start, end, refetch_days=refetch_days, today=today,
            )
        except Exception as exc:
            log.warning("Media Cloud fetch failed for cluster %d: %s", cid, exc)
            return cid, []
        return cid, recs

    # Delta-cached fetches run in a bounded thread pool (I/O-bound); each keeps its
    # own tenacity backoff so bursts respect the rate limit (ADR-068).
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        fetched = list(pool.map(_fetch, tasks))

    out: dict[int, Any] = {}
    n_heating = 0
    for cid, records in fetched:
        if not records:
            continue
        heating = press_heating(
            records,
            recent_weeks=int(heat_cfg.get("recent_weeks", 4)),
            baseline_weeks=int(heat_cfg.get("baseline_weeks", 52)),
            k=float(heat_cfg.get("k_sigma", 2.0)),
            reliable_since_year=RELIABLE_SINCE_YEAR,
        )
        if heating and heating.get("is_heating"):
            n_heating += 1
        out[cid] = MediaCloudArtifact(
            dates=[r["date"] for r in records],
            story_count=[int(r["story_count"]) for r in records],
            ratio=[float(r["ratio"]) for r in records],
            reliable_since_year=RELIABLE_SINCE_YEAR,
            caption=caption,
            granger=_press_granger(adj[cid], records),
            press_heating=heating,
        )
    log.info(
        "Built Media Cloud press overlay for %d/%d narratives (%d heating) (ADR-042/048/064/068)",
        len(out), len(fit_ids), n_heating,
    )
    return out


def _default_embedder() -> Any:
    from mnd.embedding.embedder import Embedder

    return Embedder.from_config("primary")


def _jel_scope(
    centroid_by_cid: dict[int, np.ndarray],
    cfg: dict[str, Any],
    cache_dir: Path,
    embedder: Any | None = None,
) -> dict[int, Any]:
    """Assign JEL scope by nearest-prototype on the cluster centroids (ADR-067).

    Clusters are represented by their existing centroids (mean chunk embedding from
    ``embeddings.npy``) — nothing is re-encoded per cluster. Only the fixed JEL
    prototype descriptions need embedding, and those vectors are cached on disk
    keyed on the embedder id, so on any re-run the 8B embedder is **not loaded at
    all** and scope collapses to a cosine over centroids.
    """
    import hashlib
    import pickle

    from mnd.clustering.jel_classifier import JEL_CODE_DESCRIPTIONS

    emb = cfg.get("embedding", {})
    proto_sig = hashlib.sha1(
        (
            repr(sorted(JEL_CODE_DESCRIPTIONS.items()))
            + f"{emb.get('model', '')}@{emb.get('revision', '')}"
        ).encode()
    ).hexdigest()[:12]

    cache_dir.mkdir(parents=True, exist_ok=True)
    proto_path = cache_dir / f"jel_prototypes_{proto_sig}.npy"
    prototype_vectors = None
    if proto_path.exists():
        try:
            prototype_vectors = np.load(str(proto_path))
        except Exception as exc:  # corrupt — re-embed
            log.warning("JEL prototype cache unreadable (%s); re-embedding", exc)

    embedded = False
    if prototype_vectors is None:
        if embedder is None:
            embedder = _default_embedder()
        codes = sorted(JEL_CODE_DESCRIPTIONS)
        prototype_vectors = np.asarray(
            embedder.encode([JEL_CODE_DESCRIPTIONS[c] for c in codes], show_progress=False),
            dtype=float,
        )
        np.save(str(proto_path), prototype_vectors)
        embedded = True

    jel = classify_clusters(
        cluster_terms={},
        cluster_vectors=centroid_by_cid,
        prototype_vectors=prototype_vectors,
    )
    in_scope_n = sum(1 for a in jel.values() if getattr(a, "in_scope", False))
    log.info(
        "JEL scope (ADR-067): %d/%d in-scope (E/F/G/H) via centroids; prototypes %s "
        "(out-of-scope flagged not dropped — ADR-046)",
        in_scope_n, len(jel), "embedded + cached" if embedded else "from cache",
    )
    return jel
