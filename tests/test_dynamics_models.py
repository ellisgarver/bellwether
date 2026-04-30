"""Unit tests for pure dynamics ODE functions (plan §7, no ML deps required)."""
from __future__ import annotations

import numpy as np
import pytest

from mnd.dynamics.models import (
    aicc,
    exponential,
    gompertz,
    logistic,
    logistic_r0,
    sir_peak_time,
    sir_prevalence,
    sir_r0,
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

    def test_r0_above_one_when_positive_k(self):
        r0 = logistic_r0(k=0.2, gamma=0.1)
        assert r0 > 1.0

    def test_r0_equals_one_at_zero_k(self):
        assert logistic_r0(k=0.0, gamma=0.1) == pytest.approx(1.0)


class TestSIR:
    def test_shape(self):
        I = sir_prevalence(T, N=10000, I0=10, beta=0.3, gamma=0.1)
        assert I.shape == T.shape

    def test_non_negative(self):
        I = sir_prevalence(T, N=10000, I0=10, beta=0.3, gamma=0.1)
        assert (I >= 0).all()

    def test_r0_formula(self):
        assert sir_r0(beta=0.3, gamma=0.1) == pytest.approx(3.0)

    def test_r0_below_one_no_epidemic(self):
        # R0 < 1 → I should decline monotonically
        I = sir_prevalence(T, N=10000, I0=100, beta=0.05, gamma=0.2)
        assert I[-1] < I[0]

    def test_r0_above_one_epidemic(self):
        # R0 > 1 → I should peak above initial value
        I = sir_prevalence(T, N=10000, I0=10, beta=0.5, gamma=0.1)
        assert I.max() > I[0]

    def test_peak_time_positive(self):
        pt = sir_peak_time(N=10000, I0=10, beta=0.3, gamma=0.1)
        assert pt > 0


class TestGompertz:
    def test_shape(self):
        y = gompertz(T, L=100.0, k=0.3, t0=30.0)
        assert y.shape == T.shape

    def test_bounded_by_L(self):
        y = gompertz(T, L=100.0, k=0.3, t0=30.0)
        assert y.max() <= 100.0 + 1e-10

    def test_non_negative(self):
        y = gompertz(T, L=100.0, k=0.3, t0=30.0)
        assert (y >= 0).all()


class TestExponential:
    def test_shape(self):
        from mnd.dynamics.models import exponential
        y = exponential(T, A=1.0, r=0.1)
        assert y.shape == T.shape

    def test_grows_when_r_positive(self):
        from mnd.dynamics.models import exponential
        y = exponential(T, A=1.0, r=0.1)
        assert y[-1] > y[0]

    def test_decays_when_r_negative(self):
        from mnd.dynamics.models import exponential
        y = exponential(T, A=1.0, r=-0.1)
        assert y[-1] < y[0]


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
