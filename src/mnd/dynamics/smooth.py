"""Source-stratified smoothing for narrative volume time series.

Before fitting any parametric model, smooth each source tier's weekly cluster
volume separately, then sum the smoothed tier series into the combined series
passed to the dynamics fitter.

Motivation: a single quarterly BIS publication or semi-annual IMF WEO creates a
spike confined to the institutional tier. Smoothing tier-by-tier prevents that
spike from registering as narrative acceleration in the combined series. Smoothing
the combined raw series directly would not localize the correction — it would also
damp legitimate co-movement across tiers.

Tier definitions (source_id → tier; per ADR-010 / ADR-012):
  Tier A — institutional:  federalreserve, fed_ny, fed_sf, fed_chicago,
                           fed_atlanta, fed_regional, imf, bis, cea, cbo,
                           treasury_ofr, congressional
  Tier B — academic / policy bridge:
                           voxeu, brookings, piie, cfr
                           (nber, ssrn_finance present for Phase 6 live RSS only)

Note: there is no journalism tier in the semantic corpus (ADR-010). The
journalism propagation signal is captured by the RavenPack dynamics layer
(Signal A) and not by stratified smoothing on the institutional/academic corpus.
The raw_journalism column is retained as a structural placeholder so any
unmapped source_id falls into a clearly-named bucket rather than silently
contaminating the institutional/academic series.

Smoothing:
  Centered rolling mean with window derived from config.dynamics.smoothing_window_days
  (default 7 days). For weekly-aggregated data, the effective window in weeks is
  max(window_days // 7, 1). At the config default of 7 days the window is 1
  (identity — stratification itself is the mechanism). Increase window_days to 21
  for a 3-week centered MA, 35 for 5-week, etc.

Output columns (returned DataFrame):
  week_start              date
  cluster_id              int
  raw_institutional       int   raw weekly count for Tier A sources
  raw_academic            int   raw weekly count for Tier B sources
  raw_journalism          int   raw weekly count for unmapped sources (sentinel)
  raw_combined            int   sum of all raw tier counts
  smoothed_institutional  float centered MA of raw_institutional
  smoothed_academic       float centered MA of raw_academic
  smoothed_journalism     float centered MA of raw_journalism
  smoothed_combined       float sum of three smoothed tier series

The dynamics fitter uses smoothed_combined. The dashboard displays raw_combined
as a background trace and smoothed_combined as the primary curve.
"""
from __future__ import annotations

import pandas as pd

from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)

# Source ID → smoothing tier mapping.
# Sources not listed here fall into the "journalism" bucket as a sentinel —
# the journalism tier should be empty in the active corpus (ADR-010); any
# rows that land there indicate an unmapped source_id worth flagging in QA.
TIER_SOURCES: dict[str, set[str]] = {
    "institutional": {
        "federalreserve",
        "fed_ny",
        "fed_sf",
        "fed_chicago",
        "fed_atlanta",
        "fed_regional",
        "imf",
        "bis",
        "cea",
        "cbo",
        "treasury_ofr",
        "congressional",
    },
    "academic": {
        "nber",            # Phase 6 live RSS only; harmless to map for future
        "ssrn_finance",    # Phase 6 live RSS only
        "voxeu",
        "brookings",
        "piie",
        "cfr",
    },
    "journalism": set(),   # empty under ADR-010; sentinel bucket for unmapped sources
}

# Inverted: source_id → tier label
_SOURCE_TO_TIER: dict[str, str] = {
    src: tier for tier, sources in TIER_SOURCES.items() for src in sources
}


def smooth_stratified(
    cluster_df: pd.DataFrame,
    *,
    window_days: int | None = None,
    min_periods: int = 1,
) -> pd.DataFrame:
    """Smooth narrative volume time series by source tier before combining.

    Parameters
    ----------
    cluster_df : DataFrame
        Article-level assignments. Required columns: article_id, source_id,
        published_at (ISO str or datetime), cluster_id.
        Each row is one document (not chunk). Pre-deduplicate on article_id
        before calling.
    window_days : int, optional
        Smoothing window in days. Converted to weeks for weekly data.
        Defaults to config.dynamics.smoothing_window_days (typically 7).
        Use 21 for a 3-week centered MA, 35 for 5-week.
    min_periods : int
        Minimum observations required for a non-NaN rolling result.
        Default 1 keeps edge-of-series values rather than introducing NaN.

    Returns
    -------
    DataFrame with columns: week_start, cluster_id, raw_institutional,
    raw_academic, raw_journalism, raw_combined, smoothed_institutional,
    smoothed_academic, smoothed_journalism, smoothed_combined.
    """
    if window_days is None:
        cfg = load_config()
        window_days = cfg.get("dynamics", {}).get("smoothing_window_days", 7)

    window_weeks = max(window_days // 7, 1)
    if window_weeks == 1:
        log.info(
            "smooth_stratified: window_weeks=1 (window_days=%d). "
            "Stratification applies; no temporal smoothing within tiers. "
            "Set window_days >= 21 for a 3-week centered MA.",
            window_days,
        )
    else:
        log.info("smooth_stratified: window_weeks=%d (window_days=%d)", window_weeks, window_days)

    weekly_by_source = _compute_weekly_by_source(cluster_df)
    weekly_by_tier = _assign_tiers(weekly_by_source)
    smoothed = _smooth_and_combine(weekly_by_tier, window_weeks, min_periods)
    return smoothed


def _compute_weekly_by_source(cluster_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to weekly article counts grouped by (week_start, cluster_id, source_id)."""
    df = cluster_df.copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_at"])
    df["week_start"] = (
        df["published_at"] - pd.to_timedelta(df["published_at"].dt.dayofweek, unit="D")
    ).dt.date
    weekly = (
        df.groupby(["week_start", "cluster_id", "source_id"], sort=True)
        .agg(count=("article_id", "nunique"))
        .reset_index()
    )
    return weekly


def _assign_tiers(weekly_by_source: pd.DataFrame) -> pd.DataFrame:
    """Map source_id to tier, then aggregate within tier."""
    df = weekly_by_source.copy()
    df["tier"] = df["source_id"].map(_SOURCE_TO_TIER).fillna("journalism")
    tier_weekly = (
        df.groupby(["week_start", "cluster_id", "tier"], sort=True)
        .agg(count=("count", "sum"))
        .reset_index()
    )
    # Pivot so each tier is a column
    pivoted = tier_weekly.pivot_table(
        index=["week_start", "cluster_id"],
        columns="tier",
        values="count",
        fill_value=0,
    ).reset_index()
    pivoted.columns.name = None
    # Ensure all three tier columns exist even if corpus has no records for that tier
    for tier in ("institutional", "academic", "journalism"):
        if tier not in pivoted.columns:
            pivoted[tier] = 0
    pivoted = pivoted.rename(columns={
        "institutional": "raw_institutional",
        "academic": "raw_academic",
        "journalism": "raw_journalism",
    })
    pivoted["raw_combined"] = (
        pivoted["raw_institutional"] + pivoted["raw_academic"] + pivoted["raw_journalism"]
    )
    return pivoted


def _smooth_and_combine(
    df: pd.DataFrame, window_weeks: int, min_periods: int
) -> pd.DataFrame:
    """Apply centered rolling mean per tier per cluster, then sum."""
    result_frames: list[pd.DataFrame] = []

    for cluster_id, grp in df.groupby("cluster_id", sort=False):
        grp = grp.sort_values("week_start").copy()
        for tier_col, smooth_col in (
            ("raw_institutional", "smoothed_institutional"),
            ("raw_academic", "smoothed_academic"),
            ("raw_journalism", "smoothed_journalism"),
        ):
            grp[smooth_col] = (
                grp[tier_col]
                .rolling(window=window_weeks, center=True, min_periods=min_periods)
                .mean()
            )
        grp["smoothed_combined"] = (
            grp["smoothed_institutional"]
            + grp["smoothed_academic"]
            + grp["smoothed_journalism"]
        )
        result_frames.append(grp)

    out = pd.concat(result_frames, ignore_index=True)
    # Reorder columns for clarity
    col_order = [
        "week_start", "cluster_id",
        "raw_institutional", "raw_academic", "raw_journalism", "raw_combined",
        "smoothed_institutional", "smoothed_academic", "smoothed_journalism", "smoothed_combined",
    ]
    return out[col_order]
