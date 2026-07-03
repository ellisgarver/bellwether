"""Unit tests for pure dynamics ODE functions (ADR-019, no ML deps required)."""
from __future__ import annotations

import numpy as np
import pytest

from mnd.dynamics.models import (
    _autocorr,
    aicc,
    bass,
    bass_peak_time,
    logistic,
    logistic_doubling_time,
    mann_kendall,
    shape_facts,
    sir_decay_rate,
    sir_kssir_curve,
    sir_rise_rate,
)


T = np.linspace(0, 60, 61)


class TestLogistic:
    def test_shape(self):
        y = logistic(T, L=100.0, k=0.3, t0=30.0)
        assert y.shape == T.shape

    def test_inflection_at_t0(self):
        L, k, t0 = 100.0, 0.3, 30.0
        y = logistic(T, L, k, t0)
        # Value at t0 should be L/2
        assert abs(y[30] - L / 2) < 1e-6

    def test_monotone_increasing(self):
        y = logistic(T, L=100.0, k=0.3, t0=30.0)
        assert (np.diff(y) > 0).all()

    def test_doubling_time(self):
        # doubling time = ln2 / k
        assert logistic_doubling_time(0.1) == pytest.approx(np.log(2.0) / 0.1)

    def test_doubling_time_infinite_at_zero_k(self):
        assert logistic_doubling_time(0.0) == float("inf")


class TestSIR:
    """Closed-form SIR prevalence lens (Schlickeiser & Kröger; ADR-062)."""

    def test_shape(self):
        I = sir_kssir_curve(T, peak_height=100.0, peak_time=30.0, k0=0.4, timescale=5.0)
        assert I.shape == T.shape

    def test_non_negative(self):
        I = sir_kssir_curve(T, peak_height=100.0, peak_time=30.0, k0=0.4, timescale=5.0)
        assert (I >= 0).all()

    def test_peaks_at_peak_time_and_height(self):
        I = sir_kssir_curve(T, peak_height=100.0, peak_time=30.0, k0=0.4, timescale=5.0)
        assert T[int(np.argmax(I))] == pytest.approx(30.0, abs=1.0)
        assert I.max() == pytest.approx(100.0, rel=1e-3)

    def test_asymmetry_increases_with_R0(self):
        # smaller k0 = larger R0 = more explosive rise relative to decay
        a_lo = sir_rise_rate(0.8, 5.0) / sir_decay_rate(0.8, 5.0)   # R0=1.25
        a_hi = sir_rise_rate(0.2, 5.0) / sir_decay_rate(0.2, 5.0)   # R0=5
        assert a_hi > a_lo > 1.0

    def test_rates_scale_inversely_with_timescale(self):
        assert sir_rise_rate(0.4, 10.0) == pytest.approx(0.5 * sir_rise_rate(0.4, 5.0))
        assert sir_decay_rate(0.4, 10.0) == pytest.approx(0.5 * sir_decay_rate(0.4, 5.0))


class TestBass:
    def test_shape(self):
        y = bass(T, m=1000.0, p=0.03, q=0.38)
        assert y.shape == T.shape

    def test_non_negative(self):
        y = bass(T, m=1000.0, p=0.03, q=0.38)
        assert (y >= 0).all()

    def test_interior_peak_when_imitation_dominates(self):
        # q > p → the adoption rate peaks at an interior point, not at t=0
        y = bass(T, m=1000.0, p=0.03, q=0.38)
        assert 0 < int(np.argmax(y)) < len(T) - 1

    def test_peak_time_formula_when_q_gt_p(self):
        p, q = 0.03, 0.38
        expected = np.log(q / p) / (p + q)
        assert bass_peak_time(p, q) == pytest.approx(expected)

    def test_peak_time_zero_when_innovation_dominates(self):
        # q <= p → monotonically decreasing, no interior peak
        assert bass_peak_time(p=0.4, q=0.1) == 0.0

    def test_peak_time_matches_curve_argmax(self):
        p, q = 0.03, 0.38
        t_dense = np.linspace(0, 120, 1201)
        y = bass(t_dense, m=1000.0, p=p, q=q)
        assert t_dense[int(np.argmax(y))] == pytest.approx(
            bass_peak_time(p, q), abs=1.0
        )


class TestShapeFacts:
    def test_keys_present(self):
        facts = shape_facts(T, logistic(T, 100.0, 0.3, 30.0))
        assert set(facts) == {
            "total_volume",
            "peak_volume",
            "time_to_peak_days",
            "active_days",
            "wave_count",
        }

    def test_total_volume_is_sum(self):
        y = logistic(T, 100.0, 0.3, 30.0)
        assert shape_facts(T, y)["total_volume"] == pytest.approx(float(y.sum()))

    def test_single_hump_one_wave(self):
        # A clean single bump → exactly one wave
        y = bass(T, m=1000.0, p=0.03, q=0.38)
        assert shape_facts(T, y)["wave_count"] == 1

    def test_monotone_curve_one_wave(self):
        # Rising logistic peaks at the boundary; find_peaks misses it but a single
        # hump still counts as one wave.
        y = logistic(T, 100.0, 0.3, 30.0)
        f = shape_facts(T, y)
        assert f["wave_count"] == 1
        assert f["time_to_peak_days"] == pytest.approx(T[-1])

    def test_two_humps_two_waves(self):
        # Two well-separated equal bumps above half-max → two waves
        y = (
            bass(T, m=1000.0, p=0.05, q=0.5)
            + bass(T - 35.0, m=1000.0, p=0.05, q=0.5) * (T >= 35.0)
        )
        assert shape_facts(T, y)["wave_count"] == 2

    def test_flat_zero_curve(self):
        f = shape_facts(T, np.zeros_like(T))
        assert f["wave_count"] == 0
        assert f["peak_volume"] == 0.0
        assert f["total_volume"] == 0.0

    def test_empty_series(self):
        f = shape_facts(np.array([]), np.array([]))
        assert f["wave_count"] == 0
        assert f["total_volume"] == 0.0


class TestModelSurfaceAreaPostADR019:
    """ADR-019 removed gompertz and exponential; ADR-039 added bass + shape-facts."""

    def test_gompertz_removed(self):
        import mnd.dynamics.models as m
        assert not hasattr(m, "gompertz")
        assert not hasattr(m, "exponential")
        assert not hasattr(m, "exponential_r0")

    def test_bass_and_shape_facts_present(self):
        import mnd.dynamics.models as m
        assert hasattr(m, "bass")
        assert hasattr(m, "bass_peak_time")
        assert hasattr(m, "shape_facts")


class TestAICc:
    def test_penalises_more_params(self):
        ll = -50.0
        n = 100
        # Same logL, more params → higher AICc
        assert aicc(ll, k=3, n=n) > aicc(ll, k=2, n=n)

    def test_infinite_when_n_too_small(self):
        # n - k - 1 ≤ 0 → inf
        assert aicc(-50.0, k=5, n=5) == float("inf")

    def test_finite_for_reasonable_inputs(self):
        assert np.isfinite(aicc(-100.0, k=3, n=60))


class TestAutocorr:
    def test_lag_zero_is_unity(self):
        x = np.array([3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0])
        assert _autocorr(x, nlags=3)[0] == pytest.approx(1.0)

    def test_constant_series_has_no_structure(self):
        out = _autocorr(np.ones(8), nlags=3)
        assert out[0] == 1.0
        assert (out[1:] == 0.0).all()

    def test_length_matches_nlags(self):
        assert _autocorr(np.arange(10.0), nlags=4).size == 5


class TestMannKendall:
    def test_increasing_trend_detected(self):
        rng = np.random.default_rng(42)
        y = np.arange(40.0) + rng.normal(0, 1.0, 40)
        out = mann_kendall(y)
        assert out["trend"] == "increasing"
        assert out["z"] > 0
        assert out["slope"] > 0

    def test_decreasing_trend_detected(self):
        rng = np.random.default_rng(42)
        y = (40.0 - np.arange(40.0)) + rng.normal(0, 1.0, 40)
        out = mann_kendall(y)
        assert out["trend"] == "decreasing"
        assert out["z"] < 0
        assert out["slope"] < 0

    def test_constant_series_has_no_trend(self):
        out = mann_kendall(np.ones(40))
        assert out["trend"] == "no trend"
        assert out["s"] == 0.0
        assert out["slope"] == pytest.approx(0.0)

    def test_risen_then_fell_is_not_a_monotonic_trend(self):
        # a symmetric rise-and-fall must read as "no trend" -- this is exactly the
        # shape the prior R_0-keyed scheme mislabeled as growth.
        up = np.arange(0.0, 30.0)
        down = np.arange(30.0, 0.0, -1.0)
        out = mann_kendall(np.concatenate([up, down]))
        assert out["trend"] == "no trend"

    def test_oscillation_is_not_a_trend(self):
        # a strongly autocorrelated but trendless sine exercises the Hamed-Rao
        # correction path and must not yield a false trend.
        t = np.linspace(0.0, 6.0 * np.pi, 60)
        out = mann_kendall(np.sin(t) + 5.0)
        assert out["trend"] == "no trend"

    def test_short_series_returns_no_trend(self):
        out = mann_kendall(np.array([1.0, 5.0, 3.0]))
        assert out["trend"] == "no trend"
        assert out["n"] == 3

    def test_return_keys(self):
        out = mann_kendall(np.arange(10.0))
        assert set(out) == {"trend", "p", "z", "s", "slope", "n"}
