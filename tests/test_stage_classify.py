"""Unit tests for model-free stage classification.

The stage is read off the recent shape of each narrative's own volume curve,
not off any fitted model. Four mutually-exclusive trajectory states:

  growth  -- significant upward trend in the recent window
  decay   -- significant downward trend in the recent window
  stable  -- no trend, but recent activity sits above the narrative's own floor
  dormant -- no trend and at floor

The fitted SIR R_0 is carried through for display only and must not influence
the stage; the regression guard below pins that down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from mnd.stages.classify import classify_stage

# Explicit config so the tests do not depend on config.yaml defaults: a four-week
# recent window (28 days) and the single alpha convention.
CFG = {"stages": {"trend_alpha": 0.05, "newly_emerging_recency_weeks": 4}}


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
    def test_high_plateau_above_floor_yields_stable(self):
        # quiet floor early, sustained high plateau through the recent window
        counts = _series([1.0] * 40 + [50.0] * 40)
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "stable"
        assert result.detail["trend"] == "no trend"
        assert result.detail["recent_elevated"] is True


class TestDormant:
    def test_flat_low_series_yields_dormant(self):
        counts = _series([1.0] * 60)
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "dormant"
        assert result.detail["trend"] == "no trend"
        assert result.detail["recent_elevated"] is False

    def test_risen_then_faded_to_floor_yields_dormant(self):
        # spiked early, recent window sits back at the quiet floor
        counts = _series([50.0] * 40 + [1.0] * 40)
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "dormant"
        assert result.detail["recent_elevated"] is False

    def test_too_short_series_yields_dormant(self):
        # fewer than four points: no resolvable trend, no resolvable floor
        counts = _series([1.0, 5.0, 3.0])
        result = classify_stage(0, _FitResult(), counts, cfg=CFG)
        assert result.stage == "dormant"


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
