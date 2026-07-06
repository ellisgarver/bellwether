"""Corpus-base-rate volume normalization for the dynamics layer.

Raw weekly/daily article counts confound a narrative's true spread with corpus
growth: the embedded corpus has more active sources and higher publishing
cadence in 2024 than in 2013, so a recent narrative sits on a larger denominator
of total discourse and its raw count overstates its reach. This is normalized
away with a single, global, whole-corpus base rate, expressed back in count
units so the lens fits keep working in article-count units.

For each day d:
  N(d)   = unique articles published that day across the entire embedded corpus
           (all clusters, including the BERTopic outlier bucket and out-of-scope
           clusters — the base of *all* discourse, not just in-scope macro).
  N̄(d)  = centered rolling mean of N over `smoothing_window_days` (kills the
           weekend / Mon–Fri institutional sawtooth and zero-division).
  N̄_mean = mean of N̄ over the corpus span (one scalar for the run).
  adj_c(d) = c(d) / N̄(d) * N̄_mean
           = the count cluster c would have if the corpus were always at its
             average daily size. adj_c(d) = 0 where N̄(d) == 0.

Every cluster is fit; there is no count gate, so a low-volume cluster receives a
fit with a correspondingly wide credible interval. `compute_source_contamination`
is provided as a diagnostic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mnd.utils.logging import get_logger

log = get_logger(__name__)


def _daily_unique_counts(df: pd.DataFrame, date_col: str, id_col: str) -> pd.Series:
    """Unique-article counts per calendar day (dedups chunk rows by article_id)."""
    s = df[[date_col, id_col]].copy()
    s[date_col] = pd.to_datetime(s[date_col], utc=True, errors="coerce")
    s = s.dropna(subset=[date_col])
    s["day"] = s[date_col].dt.normalize().dt.tz_localize(None)
    counts = s.groupby("day")[id_col].nunique()
    counts.index = pd.DatetimeIndex(counts.index)
    return counts.sort_index()


def corpus_base_rate(
    df: pd.DataFrame,
    *,
    date_col: str = "published_at",
    id_col: str = "article_id",
    smoothing_window_days: int = 7,
) -> tuple[pd.Series, float]:
    """Whole-corpus daily base rate N̄(d) and its mean N̄_mean (ADR-045).

    Parameters
    ----------
    df
        The full clustered corpus (chunk- or article-level; deduped on `id_col`).
        Every row across every cluster counts toward the denominator.
    smoothing_window_days
        Centered rolling-mean window for the denominator (use the same value as
        ``config.dynamics.smoothing_window_days``).

    Returns
    -------
    (base_rate, base_rate_mean)
        ``base_rate`` is N̄ over a *complete* daily DatetimeIndex spanning the
        corpus (min→max day, freq D), so per-cluster lookups never miss a day.
        ``base_rate_mean`` is the scalar N̄_mean used to re-index shares back to
        count units.
    """
    daily = _daily_unique_counts(df, date_col, id_col)
    if daily.empty:
        raise ValueError(
            "corpus_base_rate: no parseable publication dates in the corpus — "
            "cannot compute a base rate."
        )
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx, fill_value=0)
    base_rate = daily.rolling(
        window=smoothing_window_days, center=True, min_periods=1
    ).mean()
    base_rate_mean = float(base_rate[base_rate > 0].mean())
    log.info(
        "Corpus base rate: %d days, mean N̄=%.2f articles/day (window=%dd)",
        len(base_rate), base_rate_mean, smoothing_window_days,
    )
    return base_rate, base_rate_mean


def adjusted_cluster_volumes(
    df: pd.DataFrame,
    *,
    cluster_col: str = "topic",
    date_col: str = "published_at",
    id_col: str = "article_id",
    smoothing_window_days: int = 7,
    base_rate: pd.Series | None = None,
    base_rate_mean: float | None = None,
) -> dict[int, pd.Series]:
    """Corpus-adjusted daily volume per cluster (ADR-045).

    Computes the global base rate from the whole frame (unless one is supplied),
    then for each cluster returns ``adj_c(d) = c(d) / N̄(d) * N̄_mean`` over the
    cluster's own active span (min→max day it has articles, reindexed daily and
    0-filled). Fitting each cluster on its own window — not the full 16-year
    corpus grid — keeps the lifecycle shape meaningful.

    The denominator is shared across all clusters (one ``base_rate``,
    one ``base_rate_mean``), which is what makes adjusted curves directly
    comparable across narratives (the enabling invariant for future
    cross-narrative analysis, ADR-045 §3).

    Returns ``{cluster_id: adjusted_daily_series}``. The caller decides which
    cluster_ids to fit (e.g. drop the −1 outlier bucket and out-of-scope JEL).
    """
    if base_rate is None or base_rate_mean is None:
        base_rate, base_rate_mean = corpus_base_rate(
            df,
            date_col=date_col,
            id_col=id_col,
            smoothing_window_days=smoothing_window_days,
        )

    out: dict[int, pd.Series] = {}
    for cid, grp in df.groupby(cluster_col, sort=True):
        daily = _daily_unique_counts(grp, date_col, id_col)
        if daily.empty:
            continue
        span = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
        raw = daily.reindex(span, fill_value=0).astype(float)
        denom = base_rate.reindex(span).ffill().bfill()
        adj = np.where(denom.to_numpy() > 0, raw.to_numpy() / denom.to_numpy() * base_rate_mean, 0.0)
        out[int(cid)] = pd.Series(adj, index=span)
    log.info("Adjusted %d cluster volume series (corpus base-rate normalized)", len(out))
    return out


def compute_source_contamination(
    cluster_df: pd.DataFrame,
    *,
    cluster_col: str = "topic",
    contamination_threshold: float = 0.90,
) -> pd.DataFrame:
    """Source-type contamination check (retained diagnostic, ADR-045).

    For each cluster, compute the fraction of documents from each source_id.
    Clusters where any single source_id accounts for >= contamination_threshold
    of documents are flagged for manual review — they may be register-based
    (one outlet's house style) rather than genuinely semantic.

    Returns: cluster_id, dominant_source, dominant_fraction, flagged_for_review,
    total_docs.
    """
    df = cluster_df.copy()
    counts = (
        df.groupby([cluster_col, "source_id"], sort=True)
        .agg(count=("article_id", "nunique"))
        .reset_index()
    )
    totals = counts.groupby(cluster_col)["count"].sum().rename("total_docs")
    counts = counts.join(totals, on=cluster_col)
    counts["fraction"] = counts["count"] / counts["total_docs"]

    dominant = counts.loc[counts.groupby(cluster_col)["fraction"].idxmax()].copy()
    dominant = dominant.rename(
        columns={"source_id": "dominant_source", "fraction": "dominant_fraction"}
    )
    dominant["flagged_for_review"] = (
        dominant["dominant_fraction"] >= contamination_threshold
    )

    n_flagged = int(dominant["flagged_for_review"].sum())
    if n_flagged > 0:
        log.warning(
            "Source contamination: %d clusters flagged (>= %.0f%% one source). "
            "Review — may be register-based rather than semantic.",
            n_flagged, contamination_threshold * 100,
        )
    else:
        log.info("Source contamination: no clusters flagged.")

    return dominant[
        [cluster_col, "dominant_source", "dominant_fraction", "flagged_for_review", "total_docs"]
    ].reset_index(drop=True)
