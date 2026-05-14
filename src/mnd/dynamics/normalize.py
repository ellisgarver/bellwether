"""Weekly volume normalization for the dynamics layer.

ADR-008 decision:
  Express weekly article counts per narrative cluster as a fraction of
  total corpus articles that week before SIR/logistic fitting. This makes
  R₀ estimates comparable across years and absorbs corpus expansion effects.

Input:
  ravenpack_df   Weekly counts from RavenPackIngestor.fetch_volume_series()
                 Columns: week_start (date), source_id (str), article_count (int)
  cluster_df     Article-level cluster assignments from BERTopic pipeline
                 Columns: article_id, source_id, published_at, cluster_id

Output:
  normalized_df  Columns:
                   week_start       date
                   cluster_id       int
                   raw_count        int   articles in cluster that week
                   total_count      int   total corpus articles that week (RavenPack)
                   normalized_share float raw_count / total_count
                   above_threshold  bool  whether cluster meets fitting threshold

Fitting threshold (ADR-008):
  Parametric dynamics models (SIR, logistic, Gompertz) are applied ONLY when
  a cluster exceeds 3 articles/week averaged over 4 weeks AND 50 cumulative
  articles. Below threshold: descriptive stats only.

Two data sources feed this module:
  1. RavenPack volume (dynamics layer, Signal A): provides the total weekly
     corpus denominator. Covers ~800+ sources in the Dow Jones edition.
  2. Semantic corpus (embedding/clustering layer, Signal B): provides
     raw_count per cluster per week. Per ADR-010 / ADR-012 this is the
     institutional+academic+policy-bridge corpus only — no journalism tier
     (AP News, Reuters, MarketWatch are not in the semantic corpus).

The normalized_share therefore reflects semantic-corpus cluster penetration
as a fraction of the broader media ecosystem — which is the theoretically
correct quantity for measuring narrative spread.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mnd.utils.logging import get_logger

log = get_logger(__name__)

# ADR-008 thresholds
_MIN_ARTICLES_PER_WEEK_AVG = 3.0
_MIN_ROLLING_WEEKS = 4
_MIN_CUMULATIVE_ARTICLES = 50


def normalize_cluster_volumes(
    cluster_df: pd.DataFrame,
    ravenpack_df: pd.DataFrame,
    *,
    min_avg_per_week: float = _MIN_ARTICLES_PER_WEEK_AVG,
    min_rolling_weeks: int = _MIN_ROLLING_WEEKS,
    min_cumulative: int = _MIN_CUMULATIVE_ARTICLES,
) -> pd.DataFrame:
    """Compute normalized weekly cluster shares from cluster and RavenPack data.

    Parameters
    ----------
    cluster_df : DataFrame
        Must have: article_id, published_at (ISO str or datetime), cluster_id.
        Each row is one document (not chunk — dedup on article_id first).
    ravenpack_df : DataFrame
        Must have: week_start (date), source_id, article_count.
        Output of RavenPackIngestor.fetch_volume_series().
    min_avg_per_week : float
        Average weekly articles for fitting threshold.
    min_rolling_weeks : int
        Rolling window length for threshold test (in weeks).
    min_cumulative : int
        Cumulative articles for fitting threshold.

    Returns
    -------
    DataFrame with columns: week_start, cluster_id, raw_count, total_count,
    normalized_share, cumulative_count, above_threshold.
    """
    cluster_weekly = _compute_cluster_weekly(cluster_df)
    rp_weekly = _aggregate_ravenpack_weekly(ravenpack_df)
    merged = _merge_and_normalize(cluster_weekly, rp_weekly)
    merged = _apply_threshold_flag(merged, min_avg_per_week, min_rolling_weeks, min_cumulative)
    return merged


def _compute_cluster_weekly(cluster_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate cluster_df to weekly article counts per cluster."""
    df = cluster_df.copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_at"])
    # ISO week Monday as week_start
    df["week_start"] = (df["published_at"] - pd.to_timedelta(df["published_at"].dt.dayofweek, unit="D")).dt.date
    weekly = (
        df.groupby(["week_start", "cluster_id"], sort=True)
        .agg(raw_count=("article_id", "nunique"))
        .reset_index()
    )
    return weekly


def _aggregate_ravenpack_weekly(ravenpack_df: pd.DataFrame) -> pd.DataFrame:
    """Sum article counts across all sources per week."""
    rp = ravenpack_df.copy()
    rp["week_start"] = pd.to_datetime(rp["week_start"]).dt.date
    weekly = (
        rp.groupby("week_start", sort=True)
        .agg(total_count=("article_count", "sum"))
        .reset_index()
    )
    return weekly


def _merge_and_normalize(
    cluster_weekly: pd.DataFrame, rp_weekly: pd.DataFrame
) -> pd.DataFrame:
    """Join cluster counts with total corpus counts and compute share."""
    merged = cluster_weekly.merge(rp_weekly, on="week_start", how="left")
    merged["total_count"] = merged["total_count"].fillna(0).astype(int)
    # Avoid division by zero — weeks with no RavenPack coverage get NaN share
    merged["normalized_share"] = np.where(
        merged["total_count"] > 0,
        merged["raw_count"] / merged["total_count"],
        np.nan,
    )
    if merged["normalized_share"].isna().any():
        n_missing = merged["normalized_share"].isna().sum()
        log.warning(
            "%d week-cluster rows have no RavenPack total (normalized_share=NaN). "
            "Check RavenPack coverage for those weeks.",
            n_missing,
        )
    return merged


def _apply_threshold_flag(
    df: pd.DataFrame,
    min_avg_per_week: float,
    min_rolling_weeks: int,
    min_cumulative: int,
) -> pd.DataFrame:
    """Add above_threshold and cumulative_count columns per cluster."""
    df = df.sort_values(["cluster_id", "week_start"]).copy()

    results: list[pd.DataFrame] = []
    for cluster_id, grp in df.groupby("cluster_id", sort=False):
        grp = grp.sort_values("week_start").copy()
        grp["cumulative_count"] = grp["raw_count"].cumsum()
        rolling_avg = grp["raw_count"].rolling(window=min_rolling_weeks, min_periods=min_rolling_weeks).mean()
        grp["above_threshold"] = (
            (rolling_avg >= min_avg_per_week)
            & (grp["cumulative_count"] >= min_cumulative)
        )
        results.append(grp)

    out = pd.concat(results, ignore_index=True)
    out["above_threshold"] = out["above_threshold"].fillna(False)
    n_above = out.groupby("cluster_id")["above_threshold"].any().sum()
    n_total = out["cluster_id"].nunique()
    log.info(
        "Volume normalization: %d/%d clusters meet dynamics fitting threshold",
        n_above, n_total,
    )
    return out


def compute_source_contamination(
    cluster_df: pd.DataFrame,
    *,
    contamination_threshold: float = 0.90,
) -> pd.DataFrame:
    """Source-type contamination check (ADR-008 post-hoc diagnostic).

    For each cluster, compute the fraction of documents from each source_id.
    Clusters where any single source_id accounts for >= contamination_threshold
    of documents are flagged for manual review.

    Returns a DataFrame with: cluster_id, dominant_source, dominant_fraction,
    flagged_for_review, total_docs_in_cluster.
    """
    df = cluster_df.copy()
    counts = (
        df.groupby(["cluster_id", "source_id"], sort=True)
        .agg(count=("article_id", "nunique"))
        .reset_index()
    )
    totals = counts.groupby("cluster_id")["count"].sum().rename("total_docs")
    counts = counts.join(totals, on="cluster_id")
    counts["fraction"] = counts["count"] / counts["total_docs"]

    # Find dominant source per cluster
    dominant = counts.loc[counts.groupby("cluster_id")["fraction"].idxmax()].copy()
    dominant = dominant.rename(columns={"source_id": "dominant_source", "fraction": "dominant_fraction"})
    dominant["flagged_for_review"] = dominant["dominant_fraction"] >= contamination_threshold

    n_flagged = dominant["flagged_for_review"].sum()
    if n_flagged > 0:
        log.warning(
            "Source contamination: %d clusters flagged (>= %.0f%% one source). "
            "Review these manually — may be register-based rather than semantic clustering.",
            n_flagged, contamination_threshold * 100,
        )
    else:
        log.info("Source contamination: no clusters flagged.")

    return dominant[["cluster_id", "dominant_source", "dominant_fraction", "flagged_for_review", "total_docs"]].reset_index(drop=True)
