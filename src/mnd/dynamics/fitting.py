"""Bayesian dynamics fitting with PyMC.

Fits every configured lens (logistic, SIR, Bass) to a cluster's daily
article-count series and returns them all side by side; AICc is a displayed
diagnostic on each FitResult, not a selection gate. Model-free shape-facts are
computed alongside.

Stage classification no longer keys off these fits; stage is a model-free trend
test. The fits are display lenses. Each lens reports self-standing numbers in the
series' own units (ADR-062): logistic -> doubling time / inflection / plateau;
SIR -> rise rate / decay rate / asymmetry / peak; Bass -> total reach / innovation
p / imitation q. R_0 and J_inf are not reported -- neither is identifiable from a
single attention curve.

SIR model (ADR-062): the mean function is Schlickeiser & Kröger's closed-form
prevalence (an exponential rise meeting a shifted sech² decay at the peak),
elementary and differentiable, so NUTS runs at logistic/Bass cost with no ODE
solver and no scan. This replaced the former Euler scan, the analysis layer's
compute pole. Priors are data-scaled and weakly informative -- no epidemiology.

Graceful failure: genuine per-cluster convergence failures (low ESS, high R-hat,
numerical exceptions) are recorded in FitResult.failure_reason and the pipeline
continues. Programming errors that would break every cluster identically
(AttributeError, NameError, ImportError, TypeError) are re-raised rather than
swallowed, so a regression surfaces immediately instead of as silent
non-convergence across every cluster.

Configuration: config.dynamics.{inference, priors, models_to_fit}.
"""
from __future__ import annotations

import warnings
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

        # Fit the lenses on the central-mass window (ADR-060): drop the sparse
        # leading/trailing stragglers that otherwise stretch nearly every fit series
        # to ~14 years. The window carries the full active lifecycle (all waves that
        # hold real attention); only negligible-mass tails are trimmed. Each fitted
        # curve is reprojected back onto the full daily grid for display, and
        # shape-facts + staging stay on the full series.
        alpha = float(self._cfg["dynamics"].get("fit_window_mass_alpha", 0.05))
        i0, i1 = _trim_window_central_mass(y, alpha)
        t_win = np.arange(i1 - i0 + 1, dtype=float)
        y_win = y[i0:i1 + 1]

        all_fits: list[FitResult] = [
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
            sig = _lens_fit_signature(y_full, model_name, self._cfg)
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
        import pymc as pm

        priors = self._cfg["dynamics"]["priors"]["logistic"]
        inf_cfg = self._cfg["dynamics"]["inference"]

        with pm.Model() as model:
            L = pm.LogNormal("L", mu=priors["L_log_mean"], sigma=priors["L_log_sd"])
            k = pm.HalfNormal("k", sigma=priors["k_sd"])
            t0 = pm.Normal(
                "t0", mu=float(t.mean()), sigma=float(t.std() + 1.0)
            )
            sigma = pm.HalfNormal("sigma", sigma=float(y.std() + 1.0))
            mu = L / (1.0 + pm.math.exp(-k * (t - t0)))
            pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
            trace = self._sample(inf_cfg)

        import arviz as az

        summary = az.summary(trace, var_names=["L", "k", "t0"], hdi_prob=0.94)
        converged = _check_convergence(trace)
        k_mean = float(summary.loc["k", "mean"])
        L_mean = float(summary.loc["L", "mean"])
        t0_mean = float(summary.loc["t0", "mean"])
        curve = logistic(t, L_mean, k_mean, t0_mean)
        ll = _gaussian_loglik(y, curve)

        # Self-standing numbers (ADR-062): growth rate -> doubling time (days),
        # inflection date, plateau level. No R_0 (that borrowed the SIR disease
        # gamma and was not identifiable).
        params = dict(summary.to_dict())
        params["doubling_time"] = logistic_doubling_time(k_mean)
        params["inflection_day"] = t0_mean
        params["plateau"] = L_mean

        return FitResult(
            cluster_id=cluster_id,
            model_name="logistic",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            peak_time_mean=t0_mean,
            peak_time_ci_low=float(summary.loc["t0", "hdi_3%"]),
            peak_time_ci_high=float(summary.loc["t0", "hdi_97%"]),
            param_summary=params,
            curve=[float(v) for v in curve],
        )

    # ------------------------------------------------------------------
    # SIR — Schlickeiser & Kröger closed-form prevalence (ADR-062)
    # ------------------------------------------------------------------

    def _fit_sir(
        self, cluster_id: int | str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        """Fit the closed-form SIR prevalence (ADR-062): elementary, no ODE scan.

        The mean function is Schlickeiser & Kröger's analytic prevalence — an
        exponential rise meeting a shifted sech² decay at the peak — expressed in
        PyTensor so NUTS runs at logistic/Bass cost. Priors are data-scaled and
        weakly informative (no disease constants). What the lens reports is the
        rise and decay rates read off the fitted limbs; R_0 = 1/k0 is fit as a
        shape scalar but never reported (not identifiable from one curve).
        """
        import pymc as pm
        import pytensor.tensor as pt

        from mnd.dynamics.models import _SIR_ETA

        priors = self._cfg["dynamics"]["priors"]["sir"]
        inf_cfg = self._cfg["dynamics"]["sir_inference"]
        eta = _SIR_ETA
        span = float(max(len(y), 2))
        obs_peak = float(max(y.max(), 1.0))
        peak_day_guess = float(np.argmax(y))

        with pm.Model():
            # Data-scaled, weakly-informative priors (ADR-062) — no epidemiology.
            # Sampled in the DATA-IDENTIFIED coordinates (rise_rate, k0), not
            # (timescale, k0): timescale and k0 act on the curve only through their
            # combination, so sampling them directly is a curved ridge that fails to
            # mix (0/365 converged). rise_rate is pinned by the rising limb and k0 by
            # the decaying limb; timescale is derived, collapsing the ridge (ADR-062).
            peak_height = pm.LogNormal(
                "peak_height", mu=float(np.log(obs_peak)),
                sigma=float(priors["peak_height_log_sd"]),
            )
            peak_time = pm.Normal(
                "peak_time", mu=peak_day_guess, sigma=float(span / 4.0 + 1.0)
            )
            # k0 = 1/R0 in (0,1); Beta(a,b) is a gentle shape prior (a=b=2 -> centred
            # on k0=0.5, i.e. R0=2), not tuned to any anchor.
            k0 = pm.Beta("k0", alpha=float(priors["k0_beta_a"]), beta=float(priors["k0_beta_b"]))
            # Early exponential growth rate (per day), data-scaled to the window.
            rise_rate = pm.LogNormal(
                "rise_rate", mu=float(np.log(6.0 / span)),
                sigma=float(priors["rise_rate_log_sd"]),
            )
            # timescale = (1-k0)/(k0*rise_rate) since rise_rate = (1-k0)/(k0*timescale).
            timescale = (1.0 - k0) / (k0 * rise_rate)
            sigma = pm.HalfNormal("sigma", sigma=float(y.std() + 1.0))

            # Closed-form prevalence in PyTensor (mirrors models.sir_kssir_curve).
            Imax = 1.0 - k0 - k0 * pt.log((1.0 - eta) / k0)          # eq 51
            Umax = pt.log(Imax / eta)                                # eq 37
            O = Imax / k0                                            # eq 59
            kappa = 1.0 / (pt.exp(O) - 1.0)                          # eq 62
            Phi = pt.arctanh(pt.sqrt(pt.clip(1.0 - kappa * O, 0.0, 1.0 - 1e-9)))  # eq 66
            tauU = Umax * k0 / (1.0 - k0)                            # small-eta peak time
            tau = tauU + (pt.as_tensor_variable(t) - peak_time) / timescale
            rise_arg = pt.clip((tau - tauU) * (Umax / tauU), -50.0, 0.0)
            rise = peak_height * pt.exp(rise_arg)                    # eq 88
            zeta = k0 * (tau - tauU) / (2.0 * pt.sqrt(1.0 + kappa)) + Phi
            decay = peak_height * (pt.cosh(Phi) / pt.cosh(zeta)) ** 2  # eq 76
            mu = pt.switch(tau < tauU, rise, decay)

            pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
            trace = self._sample(inf_cfg)

        import arviz as az

        summary = az.summary(
            trace, var_names=["peak_height", "peak_time", "k0", "rise_rate"],
            hdi_prob=0.94,
        )
        converged = _check_convergence(trace)
        ph = float(summary.loc["peak_height", "mean"])
        pt_mean = float(summary.loc["peak_time", "mean"])
        k0_mean = float(summary.loc["k0", "mean"])
        rr_mean = float(summary.loc["rise_rate", "mean"])
        # timescale derived from the sampled (rise_rate, k0), matching the model.
        ts_mean = (1.0 - k0_mean) / (k0_mean * max(rr_mean, 1e-9))

        curve = sir_kssir_curve(t, ph, pt_mean, k0_mean, ts_mean)
        ll = _gaussian_loglik(y, curve)

        # Self-standing numbers (ADR-062): the identifiable limb rates, in per-day
        # units. rise_rate and decay_rate are the observed log-slopes; k0 and
        # timescale individually are not identifiable, but these products are.
        rise_rate = sir_rise_rate(k0_mean, ts_mean)
        decay_rate = sir_decay_rate(k0_mean, ts_mean)
        params = dict(summary.to_dict())
        params["rise_rate"] = rise_rate
        params["decay_rate"] = decay_rate
        params["doubling_time_up"] = float(np.log(2.0) / rise_rate) if rise_rate > 0 else float("inf")
        params["half_life_down"] = float(np.log(2.0) / decay_rate) if decay_rate > 0 else float("inf")
        params["asymmetry"] = float(rise_rate / decay_rate) if decay_rate > 0 else float("inf")
        params["peak_height"] = ph

        return FitResult(
            cluster_id=cluster_id,
            model_name="sir",
            converged=converged,
            aicc=aicc(ll, k=4, n=len(y)),
            peak_time_mean=pt_mean,
            peak_time_ci_low=float(summary.loc["peak_time", "hdi_3%"]),
            peak_time_ci_high=float(summary.loc["peak_time", "hdi_97%"]),
            param_summary=params,
            curve=[float(v) for v in curve],
        )

    # ------------------------------------------------------------------
    # Bass diffusion (Bass 1969) — closed form, no ODE solver needed
    # ------------------------------------------------------------------

    def _fit_bass(
        self, cluster_id: int | str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        import pymc as pm

        priors = self._cfg["dynamics"]["priors"]["bass"]
        inf_cfg = self._cfg["dynamics"]["inference"]
        m_guess = max(float(y.sum()), 1.0)

        with pm.Model():
            m = pm.LogNormal(
                "m", mu=float(np.log(m_guess)), sigma=priors["m_log_sd"]
            )
            p = pm.LogNormal("p", mu=priors["p_log_mean"], sigma=priors["p_log_sd"])
            q = pm.LogNormal("q", mu=priors["q_log_mean"], sigma=priors["q_log_sd"])
            sigma = pm.HalfNormal("sigma", sigma=float(y.std() + 1.0))

            s = p + q
            e = pm.math.exp(-s * t)
            mu = m * (s**2 / p) * e / (1.0 + (q / p) * e) ** 2
            pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
            trace = self._sample(inf_cfg)

        import arviz as az

        summary = az.summary(trace, var_names=["m", "p", "q"], hdi_prob=0.94)
        converged = _check_convergence(trace)
        m_mean = float(summary.loc["m", "mean"])
        p_mean = float(summary.loc["p", "mean"])
        q_mean = float(summary.loc["q", "mean"])
        y_hat = bass(t, m_mean, p_mean, q_mean)
        ll = _gaussian_loglik(y, y_hat)

        # Bass headline: total reach + the innovation/imitation balance.
        return FitResult(
            cluster_id=cluster_id,
            model_name="bass",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            peak_time_mean=bass_peak_time(p_mean, q_mean),
            param_summary={
                **summary.to_dict(),
                "total_reach": m_mean,
                "p_innovation": p_mean,
                "q_imitation": q_mean,
                "external_vs_internal": p_mean / max(q_mean, 1e-9),
            },
            curve=[float(v) for v in y_hat],
        )

    # ------------------------------------------------------------------
    # Shared sampling helper
    # ------------------------------------------------------------------

    def _sample(self, inf_cfg: dict[str, Any]):
        import os

        import pymc as pm

        cores = inf_cfg.get("cores", "auto")
        if cores == "auto":
            cores = min(inf_cfg["chains"], os.cpu_count() or 1)

        max_treedepth = inf_cfg.get("max_treedepth")
        common = dict(
            draws=inf_cfg["draws"],
            tune=inf_cfg["tune"],
            chains=inf_cfg["chains"],
            cores=cores,
            random_seed=inf_cfg["random_seed"],
            progressbar=False,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if max_treedepth is not None:
                # Bound leapfrog steps per draw (ADR-060 fail-fast): a cluster the
                # SIR ODE cannot fit hits the cap and is marked non-converged in
                # seconds rather than grinding at max tree depth on every draw.
                step = pm.NUTS(
                    target_accept=inf_cfg["target_accept"],
                    max_treedepth=int(max_treedepth),
                )
                return pm.sample(step=step, **common)
            return pm.sample(target_accept=inf_cfg["target_accept"], **common)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _lens_fit_signature(y_full: np.ndarray, model_name: str, cfg: dict[str, Any]) -> str:
    """Content hash of one lens's fit inputs (ADR-065).

    Covers the smoothed series, the shared fit config (smoothing window, fit-window
    alpha, global seed), and only *this lens's* priors + inference block — so a
    change to one lens's config invalidates only its cache, while the other lenses
    reload unchanged. A fixed seed keeps a cache hit identical to a refit.
    """
    import hashlib

    dyn = cfg["dynamics"]
    lens_cfg: dict[str, Any] = {
        "model": model_name,
        "smoothing": dyn.get("smoothing_window_days"),
        "fit_window_mass_alpha": dyn.get("fit_window_mass_alpha"),
        "seed": cfg["reproducibility"]["global_random_seed"],
        "priors": dyn.get("priors", {}).get(model_name),
        "inference": dyn.get("sir_inference") if model_name == "sir" else dyn.get("inference"),
    }
    payload = (
        np.ascontiguousarray(np.asarray(y_full, dtype=float)).tobytes()
        + repr(lens_cfg).encode()
    )
    return hashlib.sha1(payload).hexdigest()[:12]


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


def _check_convergence(trace) -> bool:
    """True if all R-hat < 1.05 and all bulk-ESS > 400."""
    try:
        import arviz as az

        summary = az.summary(trace)
        return bool(
            (summary["r_hat"] < 1.05).all() and (summary["ess_bulk"] > 400).all()
        )
    except Exception:
        return False


def _gaussian_loglik(y_obs: np.ndarray, y_hat: np.ndarray) -> float:
    """Gaussian log-likelihood with empirical sigma for AICc computation."""
    residuals = y_obs - y_hat
    sigma = float(residuals.std()) + 1e-6
    n = len(y_obs)
    return float(
        -n / 2.0 * np.log(2.0 * np.pi * sigma**2)
        - np.sum(residuals**2) / (2.0 * sigma**2)
    )
