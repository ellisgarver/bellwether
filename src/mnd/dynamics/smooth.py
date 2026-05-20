"""Weekly cluster volume aggregation + 7-day centered moving average.

ADR-019: the source-stratified-then-summed smoothing scheme from earlier
versions (institutional / academic / journalism tiers smoothed separately)
was removed -- the tier partition had no literature anchor and added
researcher-introduced complexity. Smoothing is now a simple 7-day centered
moving average on the combined weekly volume (Shumway & Stoffer for the
natural weekly cycle in daily count data).

Output columns:
  week_start      date
  cluster_id      int
  raw_combined    int    raw weekly article count
  smoothed_combined float centered MA of raw_combined

The dynamics fitter uses smoothed_combined. The dashboard renders
raw_combined as a background trace and smoothed_combined as the primary.
"""
from __future__ import annotations

import pandas as pd

from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)


def smooth_combined(
    cluster_df: pd.DataFrame,
    *,
    window_days: int | None = None,
    min_periods: int = 1,
) -> pd.DataFrame:
    """Aggregate to weekly per-cluster volume and apply a centered MA.

    Parameters
    ----------
    cluster_df : DataFrame
        Article-level assignments. Required columns: article_id,
        published_at (ISO str or datetime), cluster_id. One row per
        document (not chunk) -- pre-deduplicate on article_id.
    window_days : int, optional
        Smoothing window in days; converted to weeks for weekly data.
        Defaults to config.dynamics.smoothing_window_days (typically 7,
        which collapses to a 1-week window -- weekly aggregation itself
        is the primary smoothing mechanism at the default).
    min_periods : int
        Minimum observations for a non-NaN rolling result.

    Returns
    -------
    DataFrame with columns: week_start, cluster_id, raw_combined,
    smoothed_combined.
    """
    if window_days is None:
        cfg = load_config()
        window_days = cfg.get("dynamics", {}).get("smoothing_window_days", 7)

    window_weeks = max(window_days // 7, 1)
    log.info(
        "smooth_combined: window_days=%d (window_weeks=%d)", window_days, window_weeks
    )

    weekly = _compute_weekly(cluster_df)
    return _apply_rolling(weekly, window_weeks, min_periods)


def _compute_weekly(cluster_df: pd.DataFrame) -> pd.DataFrame:
    df = cluster_df.copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_at"])
    df["week_start"] = (
        df["published_at"] - pd.to_timedelta(df["published_at"].dt.dayofweek, unit="D")
    ).dt.date
    weekly = (
        df.groupby(["week_start", "cluster_id"], sort=True)
        .agg(raw_combined=("article_id", "nunique"))
        .reset_index()
    )
    return weekly


def _apply_rolling(
    df: pd.DataFrame, window_weeks: int, min_periods: int
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for _, grp in df.groupby("cluster_id", sort=False):
        grp = grp.sort_values("week_start").copy()
        grp["smoothed_combined"] = (
            grp["raw_combined"]
            .rolling(window=window_weeks, center=True, min_periods=min_periods)
            .mean()
        )
        frames.append(grp)
    out = pd.concat(frames, ignore_index=True)
    return out[["week_start", "cluster_id", "raw_combined", "smoothed_combined"]]
