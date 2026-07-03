"""Stage classification: attention trajectory -> lifecycle stage.

Model-free. The stage is read off the recent shape of the narrative's own
volume curve over a recent window W (the four-week emerging horizon, reused so no
separate window parameter is introduced):

  growth  -- significant upward trend      (modified Mann-Kendall, z > 0)
  decay   -- significant downward trend    (modified Mann-Kendall, z < 0)
  stable  -- no trend, and recent activity is still near the narrative's own
             high-water window: a high plateau
  dormant -- no trend, and recent activity has fallen below a fixed fraction of
             that peak window: faded well off its own high-water mark (ADR-058)

The trend split is a rank test (modified Mann-Kendall). The stable/dormant split
is by level, not a rank test: on the zero-heavy smoothed daily series a Mann-
Whitney comparison of two 4-week windows is under-powered (dead narratives at a
tenth of peak fail to separate), so the recent-window mean is compared to the
peak-window mean against a definitional fraction (stages.dormant_peak_fraction),
not tuned to anchor recovery (ADR-040).

The fitted lenses (logistic / SIR / Bass) are display-only and do not drive the
stage. This was always the right call: a reproduction number R_0 describes whether
a narrative ever spread, not its current phase — a present-day decline is an R_t
statement, and sign(R_t - 1) = sign(recent growth rate) regardless of the
generation interval (Wallinga & Lipsitch 2007). The model-free trend test
estimates that same crossing directly. (R_0 is no longer computed at all — it is
not identifiable from a single attention curve; ADR-062.)

"Newly emerging" is an orthogonal recency flag, not a stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

Stage = Literal["growth", "stable", "decay", "dormant"]


@dataclass
class StageClassification:
    cluster_id: int | str
    stage: Stage
    peak_time_mean: float | None
    elapsed_days: int
    detail: dict[str, Any] = field(default_factory=dict)


def _recent_faded(
    y: np.ndarray, w: int, fraction: float
) -> tuple[bool, float, float | None]:
    """Has the recent window fallen well below the narrative's own peak level?

    Distinguishes a high plateau (stable) from a faded-out series (dormant) once
    the trend test has already found no trend. The reference is the narrative's
    *loudest* equal-width stretch — its own high-water window — so each narrative
    is judged against its own dynamic range with no absolute magnitude threshold
    (ADR-058). This corrects the original floor-relative test: institutional
    sources never fully drop a topic, so "above the quiet floor" was trivially
    true and collapsed nearly every narrative to stable.

    A rank test (Mann-Whitney) on the zero-heavy smoothed daily series is under-
    powered — dead narratives at a tenth of their peak still fail to separate — so
    the comparison is by level: the recent-window mean against the peak-window
    mean. ``fraction`` is the definitional dormancy line (``stages
    .dormant_peak_fraction``): recent below ``fraction`` of peak reads dormant.
    The line is a definition, not tuned to anchor recovery (ADR-040).

    Returns (faded, recent_over_peak_ratio, peak_level). When the series is too
    short to carve out a separate peak window, or the pre-recent history is all
    zero, there is no resolvable high-water mark to have fallen from, so the result
    is not-faded and the narrative stays stable (a young series living at its only
    level has not faded).
    """
    n = y.size
    recent = y[-w:]
    if w >= n:                       # whole life inside the window: no peak to fall from
        return False, 1.0, None
    if n >= 2 * w:                   # loudest non-overlapping width-w window before recent
        starts = range(0, n - 2 * w + 1)
        s0 = max(starts, key=lambda s: float(y[s:s + w].sum()))
        peak = y[s0:s0 + w]
    else:                            # w < n < 2w: use the whole pre-recent prefix
        peak = y[: n - w]
    peak_level = float(peak.mean()) if peak.size else 0.0
    if peak_level <= 0.0 or recent.size == 0:
        return False, 1.0, peak_level or None
    ratio = float(recent.mean()) / peak_level
    return bool(ratio < fraction), ratio, peak_level


def classify_stage(
    cluster_id: int | str,
    fit_result: Any,          # FitResult from dynamics.fitting (display lens only)
    daily_counts: pd.Series,  # smoothed counts indexed by date
    cfg: dict[str, Any] | None = None,
) -> StageClassification:
    """Classify the current lifecycle stage from the narrative's volume curve.

    Model-free: a Mann-Kendall trend test plus a peak-relative level test over the
    recent window decide the stage. ``fit_result`` is carried through for SIR-lens
    display values only.
    """
    from mnd.utils.config import load_config

    from mnd.dynamics.models import mann_kendall

    if cfg is None:
        cfg = load_config()

    sc = cfg["stages"]
    alpha = float(sc.get("trend_alpha", 0.05))
    dormant_fraction = float(sc.get("dormant_peak_fraction", 0.25))
    window = int(sc["newly_emerging_recency_weeks"]) * 7

    y = np.asarray(daily_counts.to_numpy(), dtype=float)
    n = y.size
    elapsed = int(n)
    w = int(min(window, n))
    recent = y[-w:] if w > 0 else y

    mk = mann_kendall(recent, alpha=alpha)
    faded, recent_peak_ratio, peak_level = _recent_faded(y, w, dormant_fraction)

    if mk["trend"] == "increasing":
        stage: Stage = "growth"
    elif mk["trend"] == "decreasing":
        stage = "decay"
    elif not faded:
        stage = "stable"
    else:
        stage = "dormant"

    # Representative fit carried through for display only -- no longer drives the
    # stage (ADR-052), and no longer carries R_0 (dropped, ADR-062).
    peak_t = getattr(fit_result, "peak_time_mean", None) if fit_result is not None else None

    detail: dict[str, Any] = {
        "total_articles": int(daily_counts.sum()),
        "elapsed_days": elapsed,
        "window_days": w,
        # model-free trajectory diagnostics (drive the stage)
        "trend": mk["trend"],
        "trend_p": mk["p"],
        "trend_z": mk["z"],
        "trend_slope": mk["slope"],
        "recent_near_peak": bool(not faded),
        "recent_peak_ratio": recent_peak_ratio,
        "peak_level": peak_level,
        "dormant_peak_fraction": dormant_fraction,
        "alpha": alpha,
        # representative lens (display only)
        "peak_time_mean": peak_t,
        "converged": getattr(fit_result, "converged", None) if fit_result is not None else None,
    }

    return StageClassification(
        cluster_id=cluster_id,
        stage=stage,
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
