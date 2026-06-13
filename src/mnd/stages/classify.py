"""Stage classification: fitted dynamics -> lifecycle stage (ADR-019).

Three stages keyed to R_0 direction (classical SIR threshold R_0=1, Kermack &
McKendrick 1927):

  growth  -- R_0 >= config.stages.growth_min_r0 (default 1.0)
  decay   -- R_0 < growth_min_r0
  dormant -- fit did not produce a usable R_0 (no convergence, or missing)

The prior five-stage scheme (pre_emergence / early_spread / peak / decay /
dormant) used researcher-set count and window thresholds with no literature
anchor and was removed by ADR-019. "Newly emerging" is now a 4-week recency
filter on the dashboard, not a stage. The CI width on R_0 is the honest
signal of fit reliability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

Stage = Literal["growth", "decay", "dormant"]


@dataclass
class StageClassification:
    cluster_id: int | str
    stage: Stage
    r0_mean: float | None
    r0_ci_low: float | None
    r0_ci_high: float | None
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
    r0 = fit_result.r0_mean
    peak_t = fit_result.peak_time_mean

    detail: dict[str, Any] = {
        "total_articles": int(daily_counts.sum()),
        "elapsed_days": elapsed,
        "r0_mean": r0,
        "peak_time_mean": peak_t,
        "converged": fit_result.converged,
    }

    if r0 is None or not fit_result.converged:
        stage: Stage = "dormant"
    elif r0 >= sc["growth_min_r0"]:
        stage = "growth"
    else:
        stage = "decay"

    return StageClassification(
        cluster_id=cluster_id,
        stage=stage,
        r0_mean=r0,
        r0_ci_low=getattr(fit_result, "r0_ci_low", None),
        r0_ci_high=getattr(fit_result, "r0_ci_high", None),
        peak_time_mean=peak_t,
        elapsed_days=elapsed,
        detail=detail,
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
        classify_stage(cd.cluster_id, cd.staging_fit, cd.time_series, cfg)
        for cd in cluster_dynamics_list
        if cd.time_series is not None
    ]
