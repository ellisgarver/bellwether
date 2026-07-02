"""Unit tests for model-free stage classification.

The stage is read off the recent shape of each narrative's own volume curve,
not off any fitted model. Four mutually-exclusive trajectory states:

  growth  -- significant upward trend in the recent window
  decay   -- significant downward trend in the recent window
  stable  -- no trend, and recent activity is still near the narrative's own peak
  dormant -- no trend, and recent activity has fallen well below that peak (ADR-058)

The fitted SIR R_0 is carried through for display only and must not influence
the stage; the regression guard below pins that down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from mnd.stages.classify import classify_stage

# Explicit config so the tests do not depend on config.yaml defaults: a four-week
# recent window (28 days), the trend alpha, and the dormancy fraction of peak.
CFG = {
    "stages": {
        "trend_alpha": 0.05,
        "newly_emerging_recency_weeks": 4,
        "dormant_peak_fraction": 0.25,
    }
}


# Minimal FitResult stand-in so tests don't import pymc
@dataclass
class _FitResult:
    cluster_id: int | str = 0
    model_name: str = "logistic"
    converged: bool = True
    aicc: float = 0.0
    r0_mean: float | None = 1.5
    r0_median: float | None = 1.5
    r0_ci_low: float | None = None
    r0_ci_high: float | None = None
    peak_time_mean: float | None = 30.0
    peak_time_ci_low: float | None = None
    peak_time_ci_high: float | None = None
    param_summary: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2023-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx)


class TestGrowth:
    def test_rising_recent_window_yields_growth(self):
        counts = _series([float(i + 1) for i in range(60)])
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "growth"
        assert result.detail["trend"] == "increasing"
        assert result.detail["trend_slope"] > 0


class TestDecay:
    def test_falling_recent_window_yields_decay(self):
        counts = _series([float(60 - i) for i in range(60)])
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "decay"
        assert result.detail["trend"] == "decreasing"
        assert result.detail["trend_slope"] < 0


class TestStable:
    def test_high_plateau_near_peak_yields_stable(self):
        # quiet early, sustained high plateau through the recent window: recent is
        # not below the narrative's own high-water window
        counts = _series([1.0] * 40 + [50.0] * 40)
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "stable"
        assert result.detail["trend"] == "no trend"
        assert result.detail["recent_near_peak"] is True

    def test_flat_constant_series_yields_stable(self):
        # constant volume: no trend, recent equals its own peak window — never
        # rose, never faded, so it is a (low) plateau, not dormant (ADR-058)
        counts = _series([1.0] * 60)
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "stable"
        assert result.detail["trend"] == "no trend"
        assert result.detail["recent_near_peak"] is True

    def test_too_short_series_is_not_dormant(self):
        # fewer than four points: no resolvable trend and no separable peak window
        # to have fallen from, so the narrative has not faded
        counts = _series([1.0, 5.0, 3.0])
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage != "dormant"


class TestDormant:
    def test_risen_then_faded_below_peak_yields_dormant(self):
        # spiked early, recent window sits well below the narrative's own peak
        counts = _series([50.0] * 40 + [1.0] * 40)
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "dormant"
        assert result.detail["trend"] == "no trend"
        assert result.detail["recent_near_peak"] is False


class TestRZeroIsDisplayOnly:
    """R_0 is a display lens after the model-free redesign; it must not move
    the stage. A falling trajectory with a high fitted R_0 is still decay."""

    def test_high_r0_does_not_override_falling_trajectory(self):
        counts = _series([float(60 - i) for i in range(60)])
        fit = _FitResult(r0_mean=2.5, converged=True)
        result = classify_stage(0, fit, counts, cfg=CFG)
        assert result.stage == "decay"
        # the fitted value is still surfaced for display
        assert result.detail["r0_mean"] == 2.5

    def test_unconverged_fit_still_classifies_from_trajectory(self):
        counts = _series([float(i + 1) for i in range(60)])
        fit = _FitResult(r0_mean=None, converged=False)
        result = classify_stage(0, fit, counts, cfg=CFG)
        assert result.stage == "growth"

    def test_missing_fit_classifies_from_trajectory(self):
        counts = _series([float(i + 1) for i in range(60)])
        result = classify_stage(0, None, counts, cfg=CFG)
        assert result.stage == "growth"
        assert result.detail["r0_mean"] is None


class TestStageLabels:
    def test_only_four_trajectory_labels_emitted(self):
        cases = [
            _series([float(i + 1) for i in range(60)]),   # growth
            _series([float(60 - i) for i in range(60)]),  # decay
            _series([1.0] * 40 + [50.0] * 40),            # stable
            _series([1.0] * 60),                          # dormant
            _series([1.0] * 5),                           # short
        ]
        for counts in cases:
            stage = classify_stage(0, _FitResult(), counts, cfg=CFG).stage
            assert stage in {"growth", "stable", "decay", "dormant"}
