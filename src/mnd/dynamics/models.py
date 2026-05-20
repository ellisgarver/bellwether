"""Pure ODE functions for narrative dynamics models (ADR-019).

Two models:
  1. Logistic  f(t) = L / (1 + exp(-k * (t - t0)))  -- Verhulst 1838 / 3 params
  2. SIR       dS/dt = -beta*S*I/N, dI/dt = beta*S*I/N - gamma*I
                                                    -- Kermack & McKendrick 1927 / 3 params

Gompertz (1825, biological) and bare exponential have no narrative-economics
anchor and were removed by ADR-019 -- SIR's early phase already approximates
exponential growth, so adding a separate exponential model is redundant.

All functions take a float64 time array (days since first article) and return
predicted article volume. They are pure numpy/scipy and are used:
  - by fitting.py for point-estimate log-likelihoods (AICc computation)
  - by stages/classify.py for R_0 calculations
  - directly in unit tests
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import odeint


# ---------------------------------------------------------------------------
# Logistic (Verhulst 1838)
# ---------------------------------------------------------------------------

def logistic(t: np.ndarray, L: float, k: float, t0: float) -> np.ndarray:
    """Symmetric S-curve: L / (1 + exp(-k*(t-t0))).

    Deterministic limit of SIR at saturation. L = carrying capacity,
    k = growth rate, t0 = inflection (peak of derivative).
    """
    return L / (1.0 + np.exp(-k * (t - t0)))


def logistic_r0(k: float, gamma: float) -> float:
    """R_0 implied by logistic growth rate k under SIR assumptions."""
    return 1.0 + k / gamma


# ---------------------------------------------------------------------------
# SIR (Kermack & McKendrick 1927)
# ---------------------------------------------------------------------------

def _sir_rhs(y: list[float], _t: float, beta: float, gamma: float) -> list[float]:
    S, I, R = y
    N = S + I + R
    dI = beta * S * I / N - gamma * I
    return [-beta * S * I / N, dI, gamma * I]


def sir_prevalence(
    t: np.ndarray,
    N: float,
    I0: float,
    beta: float,
    gamma: float,
) -> np.ndarray:
    """Solve SIR ODE; return I(t) -- the infectious compartment.

    I(t) is interpreted as daily article volume from media nodes actively
    discussing the narrative.
    """
    I0 = max(I0, 1e-6)
    y0 = [N - I0, I0, 0.0]
    sol = odeint(_sir_rhs, y0, t, args=(beta, gamma), full_output=False)
    return np.maximum(sol[:, 1], 0.0)


def sir_r0(beta: float, gamma: float) -> float:
    return beta / gamma


def sir_peak_time(N: float, I0: float, beta: float, gamma: float) -> float:
    """Numerically locate the peak of I(t) on a dense 365-day grid."""
    t_dense = np.linspace(0, 365, 3650)
    I = sir_prevalence(t_dense, N, I0, beta, gamma)
    return float(t_dense[int(np.argmax(I))])


# ---------------------------------------------------------------------------
# AICc
# ---------------------------------------------------------------------------

def aicc(log_likelihood: float, k: int, n: int) -> float:
    """Corrected AIC: -2*logL + 2k + 2k(k+1)/(n-k-1)."""
    if n - k - 1 <= 0:
        return float("inf")
    return -2.0 * log_likelihood + 2.0 * k + 2.0 * k * (k + 1) / (n - k - 1)
