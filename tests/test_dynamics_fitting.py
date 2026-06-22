"""Unit tests for the SIR weekly-grid fit mechanics (ADR-053).

These cover the pure parts of the change -- the daily->weekly binning helper and
the config wiring -- without running NUTS, so the suite stays fast. The binning
is the load-bearing new logic: it must shorten the O(T) SIR scan while keeping
the series on daily amplitude (mean, not sum) so the population scale, priors,
and fitted I0 are unchanged, and it must report the grid factor used so the
fitted per-week rates convert back to per-day.
"""
from __future__ import annotations

import numpy as np

from mnd.dynamics.fitting import _bin_to_grid
from mnd.utils.config import load_config


class TestBinToGrid:
    def test_long_series_binned_by_grid(self):
        y = np.ones(700, dtype=float)
        binned, eff = _bin_to_grid(y, 7)
        assert eff == 7
        assert len(binned) == 100  # 700 / 7
        assert np.allclose(binned, 1.0)

    def test_block_mean_preserves_overall_mean(self):
        y = np.arange(700, dtype=float)
        binned, eff = _bin_to_grid(y, 7)
        assert eff == 7
        # Full, equal-size blocks: the mean of block means is the overall mean.
        assert np.isclose(binned.mean(), y.mean())
        assert np.isclose(binned[0], y[:7].mean())  # mean(0..6) = 3.0

    def test_mean_binning_does_not_inflate_amplitude(self):
        # A spike: averaging can never exceed the local daily maximum, so the
        # binned series stays on the same amplitude scale as the daily one.
        y = np.zeros(140, dtype=float)
        y[70] = 50.0
        binned, _ = _bin_to_grid(y, 7)
        assert binned.max() <= y.max()

    def test_ragged_tail_uses_shorter_final_block(self):
        y = np.arange(30, dtype=float)  # 30 >= 4*7, so it bins
        binned, eff = _bin_to_grid(y, 7)
        assert eff == 7
        assert len(binned) == 5  # ceil(30 / 7)
        assert np.isclose(binned[0], 3.0)        # mean(0..6)
        assert np.isclose(binned[-1], 28.5)      # mean(28, 29)

    def test_short_series_fit_on_daily_grid(self):
        y = np.arange(20, dtype=float)  # 20 < 4*7
        binned, eff = _bin_to_grid(y, 7)
        assert eff == 1
        assert np.array_equal(binned, y)

    def test_grid_one_is_passthrough(self):
        y = np.arange(50, dtype=float)
        binned, eff = _bin_to_grid(y, 1)
        assert eff == 1
        assert np.array_equal(binned, y)


class TestSirInferenceConfig:
    def test_sir_knobs_live_under_dynamics(self):
        # The fit-cache key hashes repr(cfg["dynamics"]); both knobs must sit under
        # dynamics so a change invalidates stale SIR fits (run.py _fit_signature).
        dyn = load_config()["dynamics"]
        assert "sir_fit_grid_days" in dyn
        assert "sir_inference" in dyn
        assert int(dyn["sir_fit_grid_days"]) >= 1

    def test_sir_budget_is_cheaper_than_production(self):
        dyn = load_config()["dynamics"]
        sir, base = dyn["sir_inference"], dyn["inference"]
        assert sir["draws"] < base["draws"]
        assert sir["chains"] <= base["chains"]
        assert sir["target_accept"] <= base["target_accept"]
        # _sample reads these keys; all must be present on the SIR override.
        for key in ("draws", "tune", "chains", "target_accept", "random_seed"):
            assert key in sir
