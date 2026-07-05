"""Unit tests for the least-squares fit wiring (ADR-067).

Lens fits are bounded least-squares (no PyMC/NUTS), so the whole fit layer runs
locally in milliseconds. These cover the config wiring + a real end-to-end fit.
Curve mechanics are covered in test_dynamics_models.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mnd.dynamics.fitting import DynamicsFitter, _r_squared
from mnd.dynamics.models import sir_kssir_curve
from mnd.utils.config import load_config


class TestLeastSquaresConfig:
    def test_fit_quality_gate_present(self):
        dyn = load_config()["dynamics"]
        assert 0.0 <= float(dyn["min_fit_r2"]) < 1.0

    def test_nuts_budgets_are_retired(self):
        # ADR-067 retired the MCMC budgets; their presence would signal stale config.
        dyn = load_config()["dynamics"]
        assert "inference" not in dyn
        assert "sir_inference" not in dyn


class TestLeastSquaresFit:
    def _bump(self):
        t = np.arange(140.0)
        y = np.clip(
            sir_kssir_curve(t, 80.0, 55.0, 0.4, 6.0)
            + np.random.default_rng(0).normal(0, 2.5, 140),
            0, None,
        )
        return pd.Series(y, index=pd.date_range("2022-01-01", periods=140))

    def test_all_three_lenses_fit_fast_and_report_numbers(self):
        cd = DynamicsFitter(load_config()).fit_cluster(0, self._bump())
        by = {f.model_name: f for f in cd.all_fits}
        assert set(by) == {"sir", "logistic", "bass"}
        # SIR fits the asymmetric bump well and reports the rate numbers.
        sir = by["sir"]
        assert sir.converged and sir.param_summary["r2"] > 0.9
        assert sir.param_summary["asymmetry"] > 1.0
        # Bass fits the bump too.
        assert by["bass"].converged
        # Logistic (a monotone S-curve) cannot fit a rise-and-fall bump -> grays out.
        assert not by["logistic"].converged

    def test_r_squared(self):
        y = np.array([1.0, 2.0, 3.0, 4.0])
        assert _r_squared(y, y) == 1.0
        assert _r_squared(y, np.full_like(y, y.mean())) == 0.0
