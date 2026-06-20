"""Stage classification: attention trajectory -> lifecycle stage.

Model-free. The stage is read off the recent shape of the narrative's own
volume curve with two non-parametric rank tests over a recent window W (the
four-week emerging horizon, reused so no separate parameter is tuned):

  growth  -- significant upward trend      (modified Mann-Kendall, z > 0)
  decay   -- significant downward trend    (modified Mann-Kendall, z < 0)
  stable  -- no trend, but recent activity sits significantly above the
             narrative's own quiet floor (Mann-Whitney U): a high plateau
  dormant -- no trend and at floor: faded out / unresolved

The fitted lenses (logistic / SIR / Bass) are display-only; SIR's R_0 is shown
as a "was it contagious?" headline but does not drive the stage. Keying the
stage to R_0 mislabels every risen-and-fallen narrative as growth, because
R_0 = beta/gamma is the basic reproduction number (whether it ever spread): a
current-phase decline is an R_t statement, and sign(R_t - 1) = sign(recent
growth rate) regardless of the generation interval (Wallinga & Lipsitch 2007).
The model-free trend test estimates that same crossing without the SIR machinery.

"Newly emerging" is an orthogonal recency flag, not a stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

Stage = Literal["growth", "stable", "decay", "dormant"]


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


def _recent_elevated(
    y: np.ndarray, w: int, alpha: float
) -> tuple[bool, float, float | None]:
    """Is the recent window significantly above the narrative's own quiet floor?

    Distinguishes a high plateau (stable) from a faded-out series (dormant) once
    the trend test has already found no trend. The reference is the narrative's
    quietest equal-width stretch, so each narrative is judged against its own
    dynamic range with no absolute magnitude threshold. One-sided Mann-Whitney U:
    recent activity stochastically greater than that floor.

    Returns (elevated, p_value, baseline_median). When the series is too short to
    carve out a separate baseline window there is no resolvable floor, so the
    result is not-elevated and the narrative is treated as unresolved (dormant).
    """
    n = y.size
    recent = y[-w:]
    if w >= n:                       # whole life inside the window: no floor to compare
        return False, 1.0, None
    if n >= 2 * w:                   # quietest non-overlapping width-w window before recent
        starts = range(0, n - 2 * w + 1)
        s0 = min(starts, key=lambda s: float(y[s:s + w].sum()))
        baseline = y[s0:s0 + w]
    else:                            # w < n < 2w: use the whole pre-recent prefix
        baseline = y[: n - w]
    if baseline.size == 0 or recent.size == 0:
        return False, 1.0, None
    try:
        _, p = mannwhitneyu(recent, baseline, alternative="greater")
    except ValueError:               # all-identical inputs: MWU undefined
        return False, 1.0, None
    return bool(p < alpha), float(p), float(np.median(baseline))


def classify_stage(
    cluster_id: int | str,
    fit_result: Any,          # FitResult from dynamics.fitting (display lens only)
    daily_counts: pd.Series,  # smoothed counts indexed by date
    cfg: dict[str, Any] | None = None,
) -> StageClassification:
    """Classify the current lifecycle stage from the narrative's volume curve.

    Model-free: two rank tests over the recent window decide the stage.
    ``fit_result`` is carried through for SIR-lens display values only.
    """
    from mnd.utils.config import load_config

    from mnd.dynamics.models import mann_kendall

    if cfg is None:
        cfg = load_config()

    sc = cfg["stages"]
    alpha = float(sc.get("trend_alpha", 0.05))
    window = int(sc["newly_emerging_recency_weeks"]) * 7

    y = np.asarray(daily_counts.to_numpy(), dtype=float)
    n = y.size
    elapsed = int(n)
    w = int(min(window, n))
    recent = y[-w:] if w > 0 else y

    mk = mann_kendall(recent, alpha=alpha)
    elevated, level_p, baseline_level = _recent_elevated(y, w, alpha)

    if mk["trend"] == "increasing":
        stage: Stage = "growth"
    elif mk["trend"] == "decreasing":
        stage = "decay"
    elif elevated:
        stage = "stable"
    else:
        stage = "dormant"

    # SIR lens carried through for display only -- no longer drives the stage.
    r0 = getattr(fit_result, "r0_mean", None) if fit_result is not None else None
    peak_t = getattr(fit_result, "peak_time_mean", None) if fit_result is not None else None
    r0_ci_low = getattr(fit_result, "r0_ci_low", None) if fit_result is not None else None
    r0_ci_high = getattr(fit_result, "r0_ci_high", None) if fit_result is not None else None

    detail: dict[str, Any] = {
        "total_articles": int(daily_counts.sum()),
        "elapsed_days": elapsed,
        "window_days": w,
        # model-free trajectory diagnostics (drive the stage)
        "trend": mk["trend"],
        "trend_p": mk["p"],
        "trend_z": mk["z"],
        "trend_slope": mk["slope"],
        "recent_elevated": bool(elevated),
        "level_p": level_p,
        "baseline_level": baseline_level,
        "alpha": alpha,
        # SIR lens (display only)
        "r0_mean": r0,
        "r0_median": getattr(fit_result, "r0_median", None) if fit_result is not None else None,
        "r0_ci_low": r0_ci_low,
        "r0_ci_high": r0_ci_high,
        "peak_time_mean": peak_t,
        "converged": getattr(fit_result, "converged", None) if fit_result is not None else None,
    }

    return StageClassification(
        cluster_id=cluster_id,
        stage=stage,
        r0_mean=r0,
        r0_ci_low=r0_ci_low,
        r0_ci_high=r0_ci_high,
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
