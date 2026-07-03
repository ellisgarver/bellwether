"""Unit tests for the SIR closed-form fit wiring (ADR-062).

The SIR mean function is now Schlickeiser & Kröger's closed-form prevalence (no
Euler scan / weekly grid). These cover the config wiring and the fit-cache
invariant without running NUTS, so the suite stays fast. The curve mechanics are
covered in test_dynamics_models.py.
"""
from __future__ import annotations

from mnd.utils.config import load_config


class TestSirClosedFormConfig:
    def test_sir_knobs_live_under_dynamics(self):
        # The fit-cache key hashes repr(cfg["dynamics"]); every fit knob must sit
        # under dynamics so a change invalidates stale fits (run.py _fit_signature).
        dyn = load_config()["dynamics"]
        assert "sir_inference" in dyn
        assert 0.0 < float(dyn["fit_window_mass_alpha"]) < 1.0
        assert int(dyn["sir_inference"]["max_treedepth"]) >= 1

    def test_scan_era_grid_knobs_are_retired(self):
        # ADR-062 removed the Euler-scan grid caps; their presence would signal a
        # stale config (and a stale fit path).
        dyn = load_config()["dynamics"]
        assert "sir_fit_grid_days" not in dyn
        assert "sir_max_grid_steps" not in dyn

    def test_sir_priors_are_data_scaled_not_epidemiological(self):
        # ADR-062: the Bjornstad disease beta/gamma priors are retired; the shape
        # prior is a gentle Beta on k0 and the scale priors are data-scaled sds.
        sir_pr = load_config()["dynamics"]["priors"]["sir"]
        assert {"k0_beta_a", "k0_beta_b", "peak_height_log_sd", "timescale_log_sd"} <= set(sir_pr)
        assert not ({"beta_mean", "gamma_mean"} & set(sir_pr))

    def test_sir_budget_is_cheaper_than_production(self):
        dyn = load_config()["dynamics"]
        sir, base = dyn["sir_inference"], dyn["inference"]
        assert sir["draws"] < base["draws"]
        assert sir["chains"] <= base["chains"]
        assert sir["target_accept"] <= base["target_accept"]
        for key in ("draws", "tune", "chains", "target_accept", "random_seed"):
            assert key in sir
