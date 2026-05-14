"""Stage classification: fitted dynamics → discrete lifecycle stage (plan §8).

Five stages, evaluated in strict priority order to prevent boundary ambiguity:
  pre_emergence  — cumulative articles below threshold; narrative barely present
  dormant        — trailing 14-day average ≤ dormant_max_articles_per_day
  peak           — within ±peak_window_days of fitted peak
  decay          — past peak AND ≥ decay_min_pct_below_peak of peak volume
  early_spread   — R0 ≥ 1.0 AND pre-peak
  unknown        — none of the above conditions met

All thresholds from config.stages.*. Do NOT tune to match anchor recovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

Stage = Literal["pre_emergence", "early_spread", "peak", "decay", "dormant", "unknown"]


@dataclass
class StageClassification:
    cluster_id: int | str
    stage: Stage
    confidence: float
    r0_mean: float | None
    peak_time_mean: float | None
    elapsed_days: int
    detail: dict[str, Any] = field(default_factory=dict)


def classify_stage(
    cluster_id: int | str,
    fit_result: Any,          # FitResult from dynamics.fitting
    daily_counts: pd.Series,  # smoothed counts indexed by date
    cfg: dict[str, Any] | None = None,
) -> StageClassification:
    """Classify the current lifecycle stage from a FitResult and daily counts."""
    from mnd.utils.config import load_config

    if cfg is None:
        cfg = load_config()

    sc = cfg["stages"]
    elapsed = len(daily_counts)
    total = int(daily_counts.sum())
    trailing_14 = float(
        daily_counts.iloc[-14:].mean() if elapsed >= 14 else daily_counts.mean()
    )
    current_t = float(elapsed - 1)
    r0 = fit_result.r0_mean
    peak_t = fit_result.peak_time_mean

    detail: dict[str, Any] = {
        "total_articles": total,
        "elapsed_days": elapsed,
        "trailing_14d_avg": trailing_14,
        "r0_mean": r0,
        "peak_time_mean": peak_t,
        "converged": fit_result.converged,
    }

    # Gate 1: pre-emergence
    if total <= sc["pre_emergence_max_articles"]:
        return StageClassification(
            cluster_id=cluster_id, stage="pre_emergence", confidence=1.0,
            r0_mean=r0, peak_time_mean=peak_t, elapsed_days=elapsed, detail=detail,
        )

    # Gate 2: dormant
    if trailing_14 <= sc["dormant_max_articles_per_day"]:
        return StageClassification(
            cluster_id=cluster_id, stage="dormant",
            confidence=0.85 if fit_result.converged else 0.6,
            r0_mean=r0, peak_time_mean=peak_t, elapsed_days=elapsed, detail=detail,
        )

    # Gate 3: peak
    if peak_t is not None and abs(current_t - peak_t) <= sc["peak_window_days"]:
        return StageClassification(
            cluster_id=cluster_id, stage="peak",
            confidence=0.80 if fit_result.converged else 0.5,
            r0_mean=r0, peak_time_mean=peak_t, elapsed_days=elapsed, detail=detail,
        )

    # Gate 4: decay
    if peak_t is not None and current_t > peak_t:
        peak_val = float(daily_counts.max())
        current_val = float(daily_counts.iloc[-1])
        pct_below = (peak_val - current_val) / peak_val if peak_val > 0 else 0.0
        detail["pct_below_peak"] = pct_below
        if pct_below >= sc["decay_min_pct_below_peak"]:
            return StageClassification(
                cluster_id=cluster_id, stage="decay",
                confidence=0.75 if fit_result.converged else 0.45,
                r0_mean=r0, peak_time_mean=peak_t, elapsed_days=elapsed, detail=detail,
            )

    # Gate 5: early_spread
    if r0 is not None and r0 >= sc["early_spread_min_r0"]:
        if peak_t is None or current_t < peak_t:
            return StageClassification(
                cluster_id=cluster_id, stage="early_spread",
                confidence=0.70 if fit_result.converged else 0.4,
                r0_mean=r0, peak_time_mean=peak_t, elapsed_days=elapsed, detail=detail,
            )

    return StageClassification(
        cluster_id=cluster_id, stage="unknown", confidence=0.0,
        r0_mean=r0, peak_time_mean=peak_t, elapsed_days=elapsed, detail=detail,
    )


def classify_all(
    cluster_dynamics_list: list[Any],
    cfg: dict[str, Any] | None = None,
) -> list[StageClassification]:
    """Classify stages for all ClusterDynamics objects."""
    from mnd.utils.config import load_config

    if cfg is None:
        cfg = load_config()
    return [
        classify_stage(cd.cluster_id, cd.best_fit, cd.time_series, cfg)
        for cd in cluster_dynamics_list
        if cd.time_series is not None
    ]
