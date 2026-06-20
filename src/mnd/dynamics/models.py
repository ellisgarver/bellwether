"""Pure functions for the narrative-dynamics lenses.

Four lenses, shown side by side -- each answers a different question about the
same volume curve:
  1. Logistic  f(t) = L / (1 + exp(-k * (t - t0)))  -- Verhulst 1838 / 3 params
                 "how fast did it take off, and where did it level off?"
  2. SIR       dS/dt = -beta*S*I/N, dI/dt = beta*S*I/N - gamma*I
                                          -- Kermack & McKendrick 1927 / 3 params
                 "was it contagious, and did it burn out?"  (R_0, peak)
  3. Bass      n(t) = m * f(t)            -- Bass 1969 / 3 params
                 "external shock (p) vs. word-of-mouth (q)?"
  4. shape-facts -- model-free descriptive statistics off the smoothed curve
                 "how big, how fast, how long, how many comebacks?"

Gompertz (1825, biological) and bare exponential are not included: neither has
a narrative-economics anchor, and SIR's early phase already approximates
exponential growth, so a separate exponential model would be redundant.

All curve functions take a float64 time array (days since first article) and
return predicted article volume. They are pure numpy/scipy and are used:
  - by fitting.py for point-estimate log-likelihoods (AICc computation)
  - by stages/classify.py for SIR R_0 calculations
  - directly in unit tests
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.integrate import odeint
from scipy.signal import find_peaks
from scipy.stats import norm, rankdata, theilslopes


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
# Bass diffusion (Bass 1969)
# ---------------------------------------------------------------------------

def bass(t: np.ndarray, m: float, p: float, q: float) -> np.ndarray:
    """Bass new-adopter rate n(t) = m * f(t) (Bass 1969).

    f(t) = (p+q)^2/p * e^{-(p+q)t} / (1 + (q/p) e^{-(p+q)t})^2

    p = coefficient of innovation (external influence -- a shock/event drives
        adoption independent of how many already adopted),
    q = coefficient of imitation (internal influence -- word-of-mouth, adoption
        proportional to the share who already adopted),
    m = market potential (total cumulative adopters as t -> inf).

    Returns adoptions per unit time, interpreted as daily article volume. The
    p-vs-q balance is the lens's headline: p >> q means an externally-driven
    narrative (a single event), q >> p means an organically-spreading one.
    """
    p = max(float(p), 1e-9)
    s = p + q
    e = np.exp(-s * t)
    return m * (s * s / p) * e / np.power(1.0 + (q / p) * e, 2.0)


def bass_peak_time(p: float, q: float) -> float:
    """Time of peak adoption: ln(q/p)/(p+q) when q > p, else 0 (Bass 1969).

    When imitation does not exceed innovation (q <= p) the curve is monotonically
    decreasing from t=0 -- there is no interior peak, so we report 0.
    """
    p = max(float(p), 1e-9)
    if q <= p:
        return 0.0
    return float(np.log(q / p) / (p + q))


# ---------------------------------------------------------------------------
# Shape-facts (model-free)
# ---------------------------------------------------------------------------

def shape_facts(t: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Descriptive statistics straight off the (smoothed) volume curve.

    No fitting, no assumptions -- the honest baseline a reader can always trust:
      total_volume       -- area under the curve (sum of y)
      peak_volume        -- maximum volume
      time_to_peak_days  -- t at the global maximum
      active_days        -- points with y >= peak/2 (full-width-half-max
                            convention, standard signal-processing measure)
      wave_count         -- distinct re-emergence humps: local maxima reaching
                            at least half the global peak (same half-maximum
                            convention -- no extra threshold)

    Half-maximum is the only convention used, so there is no researcher-tuned
    parameter here (ADR-019 principle 1).
    """
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)
    if y.size == 0 or float(np.max(y)) <= 0.0:
        return {
            "total_volume": float(y.sum()) if y.size else 0.0,
            "peak_volume": 0.0,
            "time_to_peak_days": 0.0,
            "active_days": 0,
            "wave_count": 0,
        }

    peak_idx = int(np.argmax(y))
    peak_volume = float(y[peak_idx])
    half = peak_volume / 2.0

    peaks, _ = find_peaks(y, height=half)
    # find_peaks ignores boundary maxima; a single rising/falling hump that peaks
    # at the first or last sample still counts as one wave.
    wave_count = int(len(peaks)) if len(peaks) > 0 else 1

    return {
        "total_volume": float(y.sum()),
        "peak_volume": peak_volume,
        "time_to_peak_days": float(t[peak_idx]),
        "active_days": int(np.sum(y >= half)),
        "wave_count": wave_count,
    }


# ---------------------------------------------------------------------------
# AICc
# ---------------------------------------------------------------------------

def aicc(log_likelihood: float, k: int, n: int) -> float:
    """Corrected AIC: -2*logL + 2k + 2k(k+1)/(n-k-1)."""
    if n - k - 1 <= 0:
        return float("inf")
    return -2.0 * log_likelihood + 2.0 * k + 2.0 * k * (k + 1) / (n - k - 1)


# ---------------------------------------------------------------------------
# Trend test (model-free)
# ---------------------------------------------------------------------------

def _autocorr(x: np.ndarray, nlags: int) -> np.ndarray:
    """Biased (divide-by-n) sample autocorrelation of x at lags 0..nlags."""
    x = np.asarray(x, dtype=float)
    n = x.size
    y = x - x.mean()
    var = float(np.dot(y, y))
    if var == 0.0:  # constant series -- no autocorrelation structure
        out = np.zeros(nlags + 1)
        out[0] = 1.0
        return out
    return np.array([float(np.dot(y[: n - k], y[k:])) for k in range(nlags + 1)]) / var


def mann_kendall(y: np.ndarray, alpha: float = 0.05) -> dict[str, Any]:
    """Modified Mann-Kendall trend test (Hamed & Rao 1998 variance correction).

    A non-parametric, rank-based test for a monotonic trend in ``y`` (Mann 1945,
    Kendall 1948). Distribution-free -- it asks only whether later values tend to
    exceed earlier ones, so a spiky attention curve does not need to look like any
    particular model for the test to apply.

    The Hamed-Rao (1998) modification inflates Var(S) to absorb serial
    correlation. This is needed here because the daily series is 7-day smoothed,
    which induces autocorrelation that would otherwise shrink the p-value and
    over-declare trends. The series is detrended with the Theil-Sen slope, the
    residuals are ranked, and Var(S) is inflated by the significant
    rank-autocorrelations.

    Returns a dict:
      trend  -- "increasing" | "decreasing" | "no trend"  (at level ``alpha``)
      p      -- two-sided p-value
      z      -- continuity-corrected standard normal statistic
      s      -- Mann-Kendall S statistic (sign-sum of all pairs)
      slope  -- Theil-Sen slope of log1p(y) per step (robust, scale-free magnitude)
      n      -- number of points used
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 4:  # too few points for the normal approximation to mean anything
        return {"trend": "no trend", "p": 1.0, "z": 0.0, "s": 0.0,
                "slope": 0.0, "n": int(n)}

    idx = np.arange(n, dtype=float)

    # --- S statistic: sum of sign(y_j - y_i) over all i < j ---
    s = 0.0
    for k in range(n - 1):
        s += float(np.sum(np.sign(y[k + 1:] - y[k])))

    # --- tie-corrected Var(S) ---
    _, counts = np.unique(y, return_counts=True)
    tie = float(np.sum(counts * (counts - 1) * (2 * counts + 5)))
    var_s = (n * (n - 1) * (2 * n + 5) - tie) / 18.0

    # --- Hamed-Rao correction: inflate Var(S) by significant rank-autocorr ---
    ts_slope = float(theilslopes(y, idx)[0])
    ranks = rankdata(y - ts_slope * idx)
    acf = _autocorr(ranks, nlags=n - 1)[1:]            # drop lag 0
    bound = norm.ppf(1 - alpha / 2.0) / np.sqrt(n)
    sig = np.where(np.abs(acf) > bound, acf, 0.0)
    cnt = 0.0
    for i in range(1, n):
        cnt += (n - i) * (n - i - 1) * (n - i - 2) * sig[i - 1]
    correction = 1.0 + (2.0 / (n * (n - 1) * (n - 2))) * cnt
    var_s *= correction

    # --- continuity-corrected standard normal statistic ---
    if var_s <= 0.0:  # degenerate (e.g. strong negative autocorr) -> conservative
        z = 0.0
    elif s > 0:
        z = (s - 1.0) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1.0) / np.sqrt(var_s)
    else:
        z = 0.0

    p = 2.0 * (1.0 - norm.cdf(abs(z)))
    slope = float(theilslopes(np.log1p(np.maximum(y, 0.0)), idx)[0])

    if p < alpha and z > 0:
        trend = "increasing"
    elif p < alpha and z < 0:
        trend = "decreasing"
    else:
        trend = "no trend"

    return {"trend": trend, "p": float(p), "z": float(z), "s": float(s),
            "slope": slope, "n": int(n)}
