"""Unit tests for stage classification (ADR-019, three-stage R0-keyed scheme).

The prior five-stage scheme (pre_emergence / early_spread / peak / decay /
dormant) used researcher-set count and window thresholds with no literature
anchor; ADR-019 reduces this to three stages keyed to the classical SIR
R_0 threshold (Kermack & McKendrick 1927).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from mnd.stages.classify import classify_stage


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


class TestGrowth:
    def test_r0_above_one_yields_growth(self):
        counts = _series([float(i + 1) for i in range(60)])
        fit = _FitResult(r0_mean=2.0, converged=True)
        result = classify_stage(0, fit, counts)
        assert result.stage == "growth"
        assert result.r0_mean == 2.0

    def test_r0_exactly_one_yields_growth(self):
        # growth_min_r0 default is 1.0 inclusive
        counts = _series([float(i + 1) for i in range(60)])
        fit = _FitResult(r0_mean=1.0, converged=True)
        result = classify_stage(0, fit, counts)
        assert result.stage == "growth"


class TestDecay:
    def test_r0_below_one_yields_decay(self):
        counts = _series([float(60 - i) for i in range(60)])
        fit = _FitResult(r0_mean=0.7, converged=True)
        result = classify_stage(0, fit, counts)
        assert result.stage == "decay"


class TestDormant:
    def test_no_r0_yields_dormant(self):
        counts = _series([1.0] * 60)
        fit = _FitResult(r0_mean=None, converged=False)
        result = classify_stage(0, fit, counts)
        assert result.stage == "dormant"

    def test_unconverged_fit_yields_dormant(self):
        # Even with R_0 > 1, unconverged means we cannot trust the fit
        counts = _series([float(i + 1) for i in range(60)])
        fit = _FitResult(r0_mean=2.0, converged=False)
        result = classify_stage(0, fit, counts)
        assert result.stage == "dormant"


class TestFiveStageRemovedPostADR019:
    """ADR-019 collapsed five stages (pre_emergence/early_spread/peak/decay/
    dormant) down to three (growth/decay/dormant). Make sure the new scheme
    never returns one of the retired labels."""

    def test_only_three_stage_labels_emitted(self):
        cases = [
            (_FitResult(r0_mean=2.0, converged=True), _series([1.0] * 5)),  # tiny series
            (_FitResult(r0_mean=0.5, converged=True), _series([1.0] * 60)),
            (_FitResult(r0_mean=None, converged=False), _series([1.0] * 60)),
        ]
        for fit, counts in cases:
            stage = classify_stage(0, fit, counts).stage
            assert stage in {"growth", "decay", "dormant"}
