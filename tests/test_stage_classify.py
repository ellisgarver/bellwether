"""Unit tests for stage classification (plan §8, no ML deps required)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pytest

from mnd.stages.classify import StageClassification, classify_stage


# Minimal FitResult stand-in so tests don't import pymc
@dataclass
class _FitResult:
    cluster_id: int | str = 0
    model_name: str = "logistic"
    converged: bool = True
    aicc: float = 0.0
    r0_mean: float | None = 1.5
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


class TestPreEmergence:
    def test_very_few_articles(self):
        counts = _series([1.0] * 10)  # total = 10 << 50 threshold
        fit = _FitResult(r0_mean=1.5, peak_time_mean=30.0)
        result = classify_stage(0, fit, counts)
        assert result.stage == "pre_emergence"
        assert result.confidence == 1.0


class TestDormant:
    def test_trailing_average_below_threshold(self):
        # 60 days, long tail near zero
        values = [50.0] * 30 + [0.5] * 30
        counts = _series(values)
        fit = _FitResult(r0_mean=None, peak_time_mean=15.0)
        result = classify_stage(0, fit, counts)
        assert result.stage == "dormant"


class TestPeak:
    def test_current_day_near_fitted_peak(self):
        # 61 days; peak at day 30; current = day 60 → not near peak
        # Make peak at day 58 so current (60) is within ±14
        values = [float(i) for i in range(30)] + [float(30 - i) for i in range(31)]
        counts = _series(values)  # total = 930 >> 50
        fit = _FitResult(r0_mean=2.0, peak_time_mean=58.0)  # within ±14 of 60
        result = classify_stage(0, fit, counts)
        assert result.stage == "peak"


class TestDecay:
    def test_past_peak_and_well_below(self):
        # Peak at day 20, then decline; current is 60% below peak
        peak_val = 100.0
        values = [float(i * 5) for i in range(21)] + [peak_val * 0.4] * 40
        counts = _series(values)
        fit = _FitResult(r0_mean=1.2, peak_time_mean=20.0)
        result = classify_stage(0, fit, counts)
        assert result.stage == "decay"


class TestEarlySpread:
    def test_r0_above_one_pre_peak(self):
        # Growing, 200 total articles, haven't reached peak yet
        values = [float(i + 1) for i in range(60)]
        counts = _series(values)
        fit = _FitResult(r0_mean=2.0, peak_time_mean=100.0)  # peak in future
        result = classify_stage(0, fit, counts)
        assert result.stage == "early_spread"

    def test_r0_below_one_yields_unknown(self):
        values = [float(i + 1) for i in range(60)]
        counts = _series(values)
        fit = _FitResult(r0_mean=0.8, peak_time_mean=None)
        result = classify_stage(0, fit, counts)
        assert result.stage == "unknown"


class TestConfidenceLowerWhenNotConverged:
    def test_unconverged_lowers_confidence(self):
        values = [float(i + 1) for i in range(60)]
        counts = _series(values)
        converged_fit = _FitResult(converged=True, r0_mean=2.0, peak_time_mean=100.0)
        unconverged_fit = _FitResult(converged=False, r0_mean=2.0, peak_time_mean=100.0)
        r_conv = classify_stage(0, converged_fit, counts)
        r_unc = classify_stage(0, unconverged_fit, counts)
        assert r_conv.confidence > r_unc.confidence
