"""Pure ODE functions for narrative dynamics models (plan §7).

Four models in increasing complexity:
  1. Exponential  f(t) = A * exp(r * t)                            — 2 params
  2. Logistic     f(t) = L / (1 + exp(-k * (t - t0)))             — 3 params
  3. Gompertz     f(t) = L * exp(-exp(-k * (t - t0)))             — 3 params
  4. SIR          dS/dt = -βSI/N, dI/dt = βSI/N - γI             — 3 params

All functions take a float64 time array (days since first article) and return
predicted article volume. They are pure numpy/scipy and are used:
  - by fitting.py for point-estimate log-likelihoods (AICc computation)
  - by stages/classify.py for peak-time and R0 calculations
  - directly in unit tests

AICc selection prefers logistic at ties (ADR-002).
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import odeint


# ---------------------------------------------------------------------------
# Exponential
# ---------------------------------------------------------------------------

def exponential(t: np.ndarray, A: float, r: float) -> np.ndarray:
    """Unconstrained growth: A * exp(r * t). For pre-emergence phases."""
    return A * np.exp(r * t)


def exponential_r0(r: float, gamma: float) -> float:
    """Approximate R0 from exponential growth rate under SIR assumptions."""
    return 1.0 + r / gamma


# ---------------------------------------------------------------------------
# Logistic
# ---------------------------------------------------------------------------

def logistic(t: np.ndarray, L: float, k: float, t0: float) -> np.ndarray:
    """Symmetric S-curve: L / (1 + exp(-k*(t-t0))).

    Deterministic limit of SIR at saturation. L = carrying capacity,
    k = growth rate, t0 = inflection (peak of derivative).
    """
    return L / (1.0 + np.exp(-k * (t - t0)))


def logistic_r0(k: float, gamma: float) -> float:
    """R0 implied by logistic growth rate k under SIR assumptions."""
    return 1.0 + k / gamma


# ---------------------------------------------------------------------------
# Gompertz
# ---------------------------------------------------------------------------

def gompertz(t: np.ndarray, L: float, k: float, t0: float) -> np.ndarray:
    """Asymmetric S-curve: L * exp(-exp(-k*(t-t0))).

    Slower approach to L than logistic; captures narratives with gradual
    late-stage saturation.
    """
    return L * np.exp(-np.exp(-k * (t - t0)))


# ---------------------------------------------------------------------------
# SIR
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
    """Solve SIR ODE; return I(t) — the infectious compartment.

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
