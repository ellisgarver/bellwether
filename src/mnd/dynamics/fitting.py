"""Least-squares dynamics fitting (ADR-067).

Fits every configured lens (logistic, SIR, Bass) to a cluster's daily
article-count series by bounded nonlinear least-squares (``scipy.least_squares``)
and returns them side by side; AICc is a displayed diagnostic on each FitResult,
not a selection gate. Model-free shape-facts are computed alongside.

The fits are display lenses reporting self-standing point numbers in the series'
own units (ADR-062): logistic -> doubling time / inflection / plateau; SIR -> rise
rate / decay rate / asymmetry / peak; Bass -> total reach / innovation p /
imitation q. R_0 and J_inf are not reported (neither is identifiable from a single
curve). Each lens is "converged" (shown) iff the optimizer succeeds and R² clears
``dynamics.min_fit_r2`` — the fit-quality gate that replaced the former MCMC
R-hat/ESS gate (ADR-067). Stage classification is model-free and does not key off
these fits.

SIR uses Schlickeiser & Kröger's closed-form prevalence (an exponential rise
meeting a shifted sech² decay; ADR-062), fit in the identifiable coordinates
(peak_height, peak_time, k0, rise_rate). No PyMC/NUTS, no ODE solver — the whole
fit layer runs in milliseconds per cluster and is fully testable locally.

Graceful failure: a per-cluster fit failure (optimizer error, degenerate series)
is recorded in FitResult.failure_reason and the pipeline continues. Programming
errors that would break every cluster identically (AttributeError, NameError,
ImportError, TypeError) are re-raised so a regression surfaces immediately.

Configuration: config.dynamics.{min_fit_r2, models_to_fit}.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from mnd.dynamics.models import (
    aicc,
    bass,
    bass_peak_time,
    logistic,
    logistic_doubling_time,
    shape_facts,
    sir_decay_rate,
    sir_kssir_curve,
    sir_rise_rate,
)
from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class FitResult:
    cluster_id: int | str
    model_name: str
    converged: bool
    aicc: float = float("inf")
    # Lens-specific self-standing numbers (ADR-062) live in ``param_summary``:
    #   logistic -> doubling_time, inflection_day, plateau
    #   sir      -> rise_rate, decay_rate, asymmetry, peak_height
    #   bass     -> total_reach, p_innovation, q_imitation, external_vs_internal
    # R_0 / J_inf are removed: not identifiable from a single attention curve.
    peak_time_mean: float | None = None
    peak_time_ci_low: float | None = None
    peak_time_ci_high: float | None = None
    param_summary: dict[str, Any] = field(default_factory=dict)
    curve: list[float] | None = None   # model prediction on the fit's daily grid (ADR-039)
    failure_reason: str | None = None


@dataclass
class ClusterDynamics:
    cluster_id: int | str
    staging_fit: FitResult        # the fit staging keys off (SIR, else logistic)
    all_fits: list[FitResult] = field(default_factory=list)  # the fitted lenses
    shape_facts: dict[str, float] = field(default_factory=dict)
    time_series: pd.Series | None = None    # smoothed daily series the fits were trained on
    raw_series: pd.Series | None = None     # observed (unsmoothed) daily volume, same index


class DynamicsFitter:
    """Fit narrative dynamics models to cluster article-count time series.

    Usage:
        fitter = DynamicsFitter.from_config()
        cd = fitter.fit_cluster(cluster_id, daily_counts_series)
    """

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self._cfg = cfg or load_config()
        # Per-lens fit-cache accounting (ADR-065), reset per _fit_with_resume run.
        self._cache_loaded = 0
        self._cache_fit = 0

    @classmethod
    def from_config(cls) -> "DynamicsFitter":
        return cls(load_config())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def smooth_series(self, series: pd.Series) -> pd.Series:
        """Centered 7-day moving average to remove weekend dips."""
        w = self._cfg["dynamics"]["smoothing_window_days"]
        return series.rolling(window=w, center=True, min_periods=1).mean()

    def fit_cluster(
        self,
        cluster_id: int | str,
        daily_counts: pd.Series,
        cache_dir: Path | None = None,
    ) -> ClusterDynamics:
        """Fit every configured lens; return all side by side (ADR-039).

        When ``cache_dir`` is given, each lens's ``FitResult`` is cached separately
        keyed on that lens's own config (ADR-065), so a change to one lens's priors
        re-fits only that lens and a re-bake reloads the rest. Staging and
        shape-facts are recomputed (cheap, model-free).
        """
        smoothed = self.smooth_series(daily_counts)
        n = len(smoothed)
        t = np.arange(n, dtype=float)
        y = smoothed.values.astype(float)

        strategy = str(self._cfg["dynamics"].get("fit_window_strategy", "central_mass"))
        if strategy == "best_third":
            all_fits = [
                self._fit_best_window(cluster_id, model_name, y, n, cache_dir)
                for model_name in self._cfg["dynamics"]["models_to_fit"]
            ]
        else:
            # central_mass (ADR-060): single window holding the central 1-alpha
            # fraction of the cumulative article mass.
            alpha = float(self._cfg["dynamics"].get("fit_window_mass_alpha", 0.05))
            i0, i1 = _trim_window_central_mass(y, alpha)
            t_win = np.arange(i1 - i0 + 1, dtype=float)
            y_win = y[i0:i1 + 1]
            all_fits = [
                self._fit_lens_cached(cluster_id, model_name, t_win, y_win, y, i0, i1, n, cache_dir)
                for model_name in self._cfg["dynamics"]["models_to_fit"]
            ]

        staging = self._select_staging_fit(cluster_id, all_fits)
        facts = shape_facts(t, y)

        log.info(
            "Cluster %s staging: %s (peak_day=%s, converged=%s); waves=%s",
            cluster_id,
            staging.model_name,
            f"{staging.peak_time_mean:.0f}" if staging.peak_time_mean is not None else "n/a",
            staging.converged,
            facts.get("wave_count"),
        )
        return ClusterDynamics(
            cluster_id=cluster_id,
            staging_fit=staging,
            all_fits=all_fits,
            shape_facts=facts,
            time_series=smoothed,
            raw_series=daily_counts,
        )

    def _fit_lens_cached(
        self,
        cluster_id: int | str,
        model_name: str,
        t_win: np.ndarray,
        y_win: np.ndarray,
        y_full: np.ndarray,
        i0: int,
        i1: int,
        n: int,
        cache_dir: Path | None,
    ) -> FitResult:
        """Fit one lens, reusing a cached reprojected FitResult when unchanged (ADR-065)."""
        import pickle

        path = None
        if cache_dir is not None:
            sig = _lens_fit_signature(y_full, model_name, self._cfg, i0, i1)
            path = cache_dir / f"fit_{cluster_id}_{model_name}_{sig}.pkl"
            if path.exists():
                try:
                    fr = pickle.loads(path.read_bytes())
                    self._cache_loaded += 1
                    return fr
                except Exception as exc:  # partial/corrupt write — refit this lens
                    log.warning(
                        "Fit cache unreadable for %s/%s (%s); refitting",
                        cluster_id, model_name, exc,
                    )
        log.info("Cluster %s — fitting %s on window [%d:%d] of %d",
                 cluster_id, model_name, i0, i1, n)
        fr = _reproject_to_full(self._fit_model(cluster_id, model_name, t_win, y_win), i0, n)
        self._cache_fit += 1
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pickle.dumps(fr))
        return fr

    def _fit_best_window(
        self,
        cluster_id: int | str,
        model_name: str,
        y: np.ndarray,
        n: int,
        cache_dir: Path | None,
    ) -> FitResult:
        """Try each candidate window; return the fit with the highest R².

        Windows must span at least 1/3 of the full series length so a trivially
        short burst cannot dominate a multi-peak history. All (model, window) pairs
        are cached independently, so repeated bakes only pay the optimizer cost on
        the first run.
        """
        min_frac = float(self._cfg["dynamics"].get("fit_window_min_frac", 1 / 3))
        n_anchors = int(self._cfg["dynamics"].get("fit_window_n_anchors", 6))
        windows = _candidate_windows(n, min_frac, n_anchors)
        best_fr: FitResult | None = None
        best_r2: float = float("-inf")
        for i0, i1 in windows:
            # Skip windows with too few non-zero points to be meaningful.
            y_win = y[i0 : i1 + 1]
            if float(np.sum(y_win > 0)) < 5 or float(np.max(y_win)) <= 0:
                continue
            t_win = np.arange(i1 - i0 + 1, dtype=float)
            fr = self._fit_lens_cached(
                cluster_id, model_name, t_win, y_win, y, i0, i1, n, cache_dir
            )
            # Converged fits are ranked by R²; non-converged are ranked below -1
            # so a bad converged fit still beats no converged fit at all.
            r2 = float(fr.param_summary.get("r2", -1.0)) if fr.converged else -2.0
            if r2 > best_r2:
                best_r2 = r2
                best_fr = fr
        if best_fr is not None:
            return best_fr
        # No window converged — return the central-mass fit as a fallback so the
        # lens tab still shows the unconverged curve rather than nothing.
        alpha = float(self._cfg["dynamics"].get("fit_window_mass_alpha", 0.05))
        i0_fb, i1_fb = _trim_window_central_mass(y, alpha)
        t_fb = np.arange(i1_fb - i0_fb + 1, dtype=float)
        return self._fit_lens_cached(
            cluster_id, model_name, t_fb, y[i0_fb : i1_fb + 1],
            y, i0_fb, i1_fb, n, cache_dir,
        )

    @staticmethod
    def _select_staging_fit(
        cluster_id: int | str, all_fits: list[FitResult]
    ) -> FitResult:
        """Pick the representative fit carried on the narrative (display only).

        Prefer the converged SIR fit (its rise/decay asymmetry is the "how did it
        spread and fade?" view), else the converged logistic fit, else any fit.
        This no longer decides the stage; that is the model-free trend test.
        """
        by_name = {f.model_name: f for f in all_fits}
        sir_fit = by_name.get("sir")
        log_fit = by_name.get("logistic")
        if sir_fit is not None and sir_fit.converged:
            return sir_fit
        if log_fit is not None and log_fit.converged:
            return log_fit
        if sir_fit is not None:
            return sir_fit
        if log_fit is not None:
            return log_fit
        if all_fits:
            return all_fits[0]
        return FitResult(
            cluster_id=cluster_id,
            model_name="none",
            converged=False,
            failure_reason="no models configured",
        )

    # ------------------------------------------------------------------
    # Model dispatch
    # ------------------------------------------------------------------

    def _fit_model(
        self, cluster_id: int | str, model_name: str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        try:
            if model_name == "logistic":
                return self._fit_logistic(cluster_id, t, y)
            if model_name == "sir":
                return self._fit_sir(cluster_id, t, y)
            if model_name == "bass":
                return self._fit_bass(cluster_id, t, y)
            return FitResult(
                cluster_id=cluster_id,
                model_name=model_name,
                converged=False,
                failure_reason=f"Unknown model: {model_name}",
            )
        except (AttributeError, NameError, ImportError, TypeError):
            # Programming errors (bad attribute, missing import, wrong signature)
            # are not per-cluster convergence failures; they break every cluster
            # identically. Re-raising surfaces such a regression immediately rather
            # than recording it as silent non-convergence across the whole corpus.
            raise
        except Exception as exc:
            log.warning(
                "Cluster %s model %s failed: %s", cluster_id, model_name, exc
            )
            return FitResult(
                cluster_id=cluster_id,
                model_name=model_name,
                converged=False,
                failure_reason=str(exc),
            )

    # ------------------------------------------------------------------
    # Logistic
    # ------------------------------------------------------------------

    def _fit_logistic(
        self, cluster_id: int | str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        """Least-squares logistic fit (ADR-067) — point estimates + curve, no NUTS."""
        from scipy.optimize import least_squares

        L0 = max(float(y.max()), 1.0)
        x0 = [L0, 0.1, float(t.mean())]
        lo = [1e-6, 1e-4, float(t.min())]
        hi = [L0 * 10.0 + 1.0, 5.0, float(t.max())]
        res = least_squares(
            lambda p: logistic(t, *p) - y, x0, bounds=(lo, hi),
            method="trf", max_nfev=2000,
        )
        L, k, t0 = (float(v) for v in res.x)
        curve = logistic(t, L, k, t0)
        r2 = _r_squared(y, curve)
        converged = bool(res.success and r2 >= self._min_fit_r2())
        ll = _gaussian_loglik(y, curve)

        # Self-standing numbers (ADR-062): growth rate -> doubling time (days),
        # inflection date, plateau level.
        params = {
            "L": L, "k": k, "t0": t0, "r2": r2,
            "doubling_time": logistic_doubling_time(k),
            "inflection_day": t0,
            "plateau": L,
        }
        return FitResult(
            cluster_id=cluster_id,
            model_name="logistic",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            peak_time_mean=t0,
            param_summary=params,
            curve=[float(v) for v in curve],
        )

    # ------------------------------------------------------------------
    # SIR — Schlickeiser & Kröger closed-form prevalence (ADR-062)
    # ------------------------------------------------------------------

    def _fit_sir(
        self, cluster_id: int | str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        """Least-squares closed-form SIR fit (ADR-062/067) — no ODE, no NUTS.

        Fits Schlickeiser & Kröger's analytic prevalence (exponential rise meeting a
        shifted sech² decay) in the data-identified coordinates (peak_height,
        peak_time, k0, rise_rate); timescale = (1-k0)/(k0·rise_rate) is derived. The
        lens reports the rise/decay rates read off the fitted limbs; R_0 = 1/k0 is a
        shape scalar, never reported (not identifiable from one curve).
        """
        from scipy.optimize import least_squares

        span = float(max(len(y), 2))
        obs_peak = float(max(y.max(), 1.0))
        peak_day_guess = float(np.argmax(y))

        def curve_of(p):
            ph, ptime, k0, rr = p
            ts = (1.0 - k0) / (k0 * max(rr, 1e-9))
            return sir_kssir_curve(t, ph, ptime, k0, ts)

        x0 = [obs_peak, peak_day_guess, 0.5, 6.0 / span]
        lo = [1e-6, float(t.min()), 0.02, 1e-4]
        hi = [obs_peak * 10.0 + 1.0, float(t.max()), 0.98, 5.0]
        res = least_squares(
            lambda p: curve_of(p) - y, x0, bounds=(lo, hi),
            method="trf", max_nfev=3000,
        )
        ph, ptime, k0, rr = (float(v) for v in res.x)
        ts = (1.0 - k0) / (k0 * max(rr, 1e-9))
        curve = sir_kssir_curve(t, ph, ptime, k0, ts)
        r2 = _r_squared(y, curve)
        converged = bool(res.success and r2 >= self._min_fit_r2())
        ll = _gaussian_loglik(y, curve)

        rise_rate = sir_rise_rate(k0, ts)
        decay_rate = sir_decay_rate(k0, ts)
        params = {
            "peak_height": ph, "peak_time": ptime, "k0": k0, "r2": r2,
            "rise_rate": rise_rate,
            "decay_rate": decay_rate,
            "doubling_time_up": float(np.log(2.0) / rise_rate) if rise_rate > 0 else float("inf"),
            "half_life_down": float(np.log(2.0) / decay_rate) if decay_rate > 0 else float("inf"),
            "asymmetry": float(rise_rate / decay_rate) if decay_rate > 0 else float("inf"),
        }
        return FitResult(
            cluster_id=cluster_id,
            model_name="sir",
            converged=converged,
            aicc=aicc(ll, k=4, n=len(y)),
            peak_time_mean=ptime,
            param_summary=params,
            curve=[float(v) for v in curve],
        )

    # ------------------------------------------------------------------
    # Bass diffusion (Bass 1969) — closed form, no ODE solver needed
    # ------------------------------------------------------------------

    def _fit_bass(
        self, cluster_id: int | str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        """Least-squares Bass fit (ADR-067) — closed form, no NUTS.

        Priors are retired to init values anchored to the Sultan–Farley–Lehmann 1990
        meta-analysis means (p≈0.03 innovation, q≈0.38 imitation), which now seed the
        optimizer rather than regularize a posterior.
        """
        from scipy.optimize import least_squares

        priors = self._cfg["dynamics"]["priors"]["bass"]
        m0 = max(float(y.sum()), 1.0)
        # Init p, q from the Sultan–Farley–Lehmann 1990 meta-analysis means (ADR-067).
        x0 = [m0, float(np.exp(priors["p_log_mean"])), float(np.exp(priors["q_log_mean"]))]
        lo = [1e-6, 1e-5, 1e-5]
        hi = [m0 * 10.0 + 1.0, 2.0, 5.0]
        res = least_squares(
            lambda p: bass(t, *p) - y, x0, bounds=(lo, hi),
            method="trf", max_nfev=3000,
        )
        m, p, q = (float(v) for v in res.x)
        curve = bass(t, m, p, q)
        r2 = _r_squared(y, curve)
        converged = bool(res.success and r2 >= self._min_fit_r2())
        ll = _gaussian_loglik(y, curve)

        # Bass headline: total reach + the innovation/imitation balance.
        return FitResult(
            cluster_id=cluster_id,
            model_name="bass",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            peak_time_mean=bass_peak_time(p, q),
            param_summary={
                "m": m, "p": p, "q": q, "r2": r2,
                "total_reach": m,
                "p_innovation": p,
                "q_imitation": q,
                "external_vs_internal": p / max(q, 1e-9),
            },
            curve=[float(v) for v in curve],
        )

    def _min_fit_r2(self) -> float:
        """Fit-quality floor: a lens is 'converged' (shown) iff its R² clears this."""
        return float(self._cfg["dynamics"].get("min_fit_r2", 0.3))


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _lens_fit_signature(
    y_full: np.ndarray,
    model_name: str,
    cfg: dict[str, Any],
    i0: int = 0,
    i1: int = -1,
) -> str:
    """Content hash of one lens's fit inputs (ADR-065).

    Covers the smoothed series, the shared fit config (smoothing window, fit-window
    strategy + alpha, the R² display floor), only *this lens's* priors, and the
    specific window [i0, i1] — so each (model, window) pair gets its own cache
    file, and a change to one lens's config invalidates only its cache.
    The fits are deterministic least squares (ADR-067), so a cache hit is
    identical to a refit.
    """
    import hashlib

    dyn = cfg["dynamics"]
    lens_cfg: dict[str, Any] = {
        "model": model_name,
        "smoothing": dyn.get("smoothing_window_days"),
        "fit_window_strategy": dyn.get("fit_window_strategy", "central_mass"),
        "fit_window_mass_alpha": dyn.get("fit_window_mass_alpha"),
        "min_fit_r2": dyn.get("min_fit_r2"),
        "priors": dyn.get("priors", {}).get(model_name),  # bass init anchors (ADR-067)
        "window": [i0, int(i1)],
    }
    payload = (
        np.ascontiguousarray(np.asarray(y_full, dtype=float)).tobytes()
        + repr(lens_cfg).encode()
    )
    return hashlib.sha1(payload).hexdigest()[:12]


def _candidate_windows(
    n: int, min_frac: float = 1 / 3, n_anchors: int = 6
) -> list[tuple[int, int]]:
    """Generate diverse [i0, i1] fit windows each spanning at least ``min_frac`` of n.

    Places ``n_anchors`` evenly-spaced anchor points across the series and returns
    all pairs (a0, a1) where a1 - a0 >= min_frac * n.  Always includes the full
    range [0, n-1] as a fallback.
    """
    if n < 2:
        return [(0, max(0, n - 1))]
    min_len = max(int(n * min_frac), 30)
    step = max(1, n // (n_anchors - 1))
    anchors = sorted(set(min(i * step, n - 1) for i in range(n_anchors)) | {n - 1})
    seen: set[tuple[int, int]] = set()
    windows: list[tuple[int, int]] = []
    for a0 in anchors:
        for a1 in anchors:
            if a1 - a0 < min_len:
                continue
            if (a0, a1) not in seen:
                seen.add((a0, a1))
                windows.append((a0, a1))
    if not windows:
        windows.append((0, n - 1))
    return windows


def _trim_window_central_mass(y: np.ndarray, alpha: float) -> tuple[int, int]:
    """Index window ``[i0, i1]`` holding the central ``1 - alpha`` of cumulative mass.

    The lens fit window (ADR-060). Drops the sparse leading/trailing stragglers — a
    lone article years before or after the active life — that otherwise stretch the
    fit series across the whole corpus and destabilise the SIR scan. Every wave that
    carries real attention sits inside the central band, so multi-wave narratives
    keep all their humps; only negligible-mass tails are cut. "Central ``1 - alpha``"
    is a standard convention and reuses the project ``alpha`` — no new tuned
    parameter. Degenerate (empty or all-zero) series return the full range.
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n == 0:
        return 0, 0
    c = np.cumsum(np.clip(y, 0.0, None))
    total = float(c[-1])
    if total <= 0.0:
        return 0, n - 1
    c = c / total
    i0 = int(np.searchsorted(c, alpha / 2.0, side="left"))
    i1 = int(np.searchsorted(c, 1.0 - alpha / 2.0, side="left"))
    i0 = min(i0, n - 1)
    i1 = max(min(i1, n - 1), i0)
    return i0, i1


def _reproject_to_full(fr: FitResult, i0: int, n: int) -> FitResult:
    """Place a window-local fit back on the full daily grid (ADR-060).

    The lenses are fit on the central-mass window; the curve is padded with ``None``
    before and after the window so it aligns with the full displayed volume series,
    and peak-time values are shifted by the window offset ``i0`` into full-grid day
    units. Non-converged fits (no curve) just get the peak-time offset.
    """
    if fr.curve is not None:
        head: list[float | None] = [None] * i0
        tail: list[float | None] = [None] * (n - i0 - len(fr.curve))
        fr.curve = head + list(fr.curve) + tail
    for attr in ("peak_time_mean", "peak_time_ci_low", "peak_time_ci_high"):
        v = getattr(fr, attr, None)
        if v is not None:
            setattr(fr, attr, float(v) + i0)
    return fr


def _r_squared(y_obs: np.ndarray, y_hat: np.ndarray) -> float:
    """Coefficient of determination — the least-squares fit-quality metric (ADR-067)."""
    y_obs = np.asarray(y_obs, dtype=float)
    ss_res = float(np.sum((y_obs - np.asarray(y_hat, dtype=float)) ** 2))
    ss_tot = float(np.sum((y_obs - y_obs.mean()) ** 2))
    if ss_tot <= 0.0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def _gaussian_loglik(y_obs: np.ndarray, y_hat: np.ndarray) -> float:
    """Gaussian log-likelihood with empirical sigma for AICc computation."""
    residuals = y_obs - y_hat
    sigma = float(residuals.std()) + 1e-6
    n = len(y_obs)
    return float(
        -n / 2.0 * np.log(2.0 * np.pi * sigma**2)
        - np.sum(residuals**2) / (2.0 * sigma**2)
    )
