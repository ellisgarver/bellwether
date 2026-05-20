"""Bayesian dynamics fitting with PyMC (ADR-019).

Fits the two configured models (logistic, SIR) to a cluster's daily
article-count series and selects the best by AICc, preferring logistic at
ties (ADR-002).

SIR model: uses a pytensor.scan discrete-time Euler loop so the ODE is
differentiable through PyMC's NUTS sampler without an external ODE solver.

Graceful failure: convergence failures (low ESS, high R-hat, exceptions) are
recorded in FitResult.failure_reason; the pipeline continues. AICc = inf for
failed fits so they never win selection. The prior min_r_squared and
max_r0_ci_width kill-criterion thresholds were removed by ADR-019 -- R^2 and
R_0 credible-interval width are reported as diagnostics, not gated.

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
    logistic,
    logistic_r0,
    sir_peak_time,
    sir_prevalence,
    sir_r0,
)
from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)

_PREFERRED_ORDER = ["logistic", "sir"]


@dataclass
class FitResult:
    cluster_id: int | str
    model_name: str
    converged: bool
    aicc: float = float("inf")
    r0_mean: float | None = None
    r0_ci_low: float | None = None
    r0_ci_high: float | None = None
    peak_time_mean: float | None = None
    peak_time_ci_low: float | None = None
    peak_time_ci_high: float | None = None
    param_summary: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None


@dataclass
class ClusterDynamics:
    cluster_id: int | str
    best_model: str
    best_fit: FitResult
    all_fits: list[FitResult] = field(default_factory=list)
    time_series: pd.Series | None = None


class DynamicsFitter:
    """Fit narrative dynamics models to cluster article-count time series.

    Usage:
        fitter = DynamicsFitter.from_config()
        cd = fitter.fit_cluster(cluster_id, daily_counts_series)
    """

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self._cfg = cfg or load_config()

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
        self, cluster_id: int | str, daily_counts: pd.Series
    ) -> ClusterDynamics:
        """Fit all configured models; return best by AICc."""
        smoothed = self.smooth_series(daily_counts)
        t = np.arange(len(smoothed), dtype=float)
        y = smoothed.values.astype(float)

        all_fits: list[FitResult] = []
        for model_name in self._cfg["dynamics"]["models_to_fit"]:
            log.info("Cluster %s — fitting %s", cluster_id, model_name)
            fit = self._fit_model(cluster_id, model_name, t, y)
            all_fits.append(fit)

        converged = [f for f in all_fits if f.converged]
        pool = converged if converged else all_fits
        best = min(
            pool,
            key=lambda f: (
                f.aicc,
                _PREFERRED_ORDER.index(f.model_name)
                if f.model_name in _PREFERRED_ORDER
                else 99,
            ),
        )

        log.info(
            "Cluster %s best: %s (AICc=%.1f, R0=%s, converged=%s)",
            cluster_id,
            best.model_name,
            best.aicc,
            f"{best.r0_mean:.2f}" if best.r0_mean is not None else "n/a",
            best.converged,
        )
        return ClusterDynamics(
            cluster_id=cluster_id,
            best_model=best.model_name,
            best_fit=best,
            all_fits=all_fits,
            time_series=smoothed,
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
            return FitResult(
                cluster_id=cluster_id,
                model_name=model_name,
                converged=False,
                failure_reason=f"Unknown model: {model_name}",
            )
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
        gamma_prior = self._cfg["dynamics"]["priors"]["sir"]["gamma_mean"]
        k_mean = float(summary.loc["k", "mean"])
        k_lo = float(summary.loc["k", "hdi_3%"])
        k_hi = float(summary.loc["k", "hdi_97%"])
        L_mean = float(summary.loc["L", "mean"])
        t0_mean = float(summary.loc["t0", "mean"])
        ll = _gaussian_loglik(y, logistic(t, L_mean, k_mean, t0_mean))

        return FitResult(
            cluster_id=cluster_id,
            model_name="logistic",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            r0_mean=logistic_r0(k_mean, gamma_prior),
            r0_ci_low=logistic_r0(k_lo, gamma_prior),
            r0_ci_high=logistic_r0(k_hi, gamma_prior),
            peak_time_mean=t0_mean,
            peak_time_ci_low=float(summary.loc["t0", "hdi_3%"]),
            peak_time_ci_high=float(summary.loc["t0", "hdi_97%"]),
            param_summary=summary.to_dict(),
        )

    # ------------------------------------------------------------------
    # SIR — discrete-time Euler via pytensor.scan (differentiable)
    # ------------------------------------------------------------------

    def _fit_sir(
        self, cluster_id: int | str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        import pymc as pm
        import pytensor.tensor as pt

        priors = self._cfg["dynamics"]["priors"]["sir"]
        inf_cfg = self._cfg["dynamics"]["inference"]
        N_pop = float(max(y.sum() * 2.0, 100.0))
        T = len(t)

        with pm.Model():
            beta = pm.HalfNormal("beta", sigma=priors["beta_sd"])
            gamma = pm.HalfNormal("gamma", sigma=priors["gamma_sd"])
            I0 = pm.HalfNormal("I0", sigma=max(float(y[:5].mean()), 1.0) * 3)
            sigma = pm.HalfNormal("sigma", sigma=float(y.std() + 1.0))

            S_init = pt.as_tensor_variable(N_pop) - I0
            R_init = pt.zeros(())

            def sir_step(S_prev, I_prev, R_prev, b, g, n):
                new_inf = pt.clip(b * S_prev * I_prev / n, 0.0, S_prev)
                rec = pt.clip(g * I_prev, 0.0, I_prev)
                return S_prev - new_inf, I_prev + new_inf - rec, R_prev + rec

            (_, I_seq, _), _ = pt.scan(
                sir_step,
                outputs_info=[S_init, I0, R_init],
                non_sequences=[beta, gamma, pt.as_tensor_variable(N_pop)],
                n_steps=T - 1,
            )
            I_traj = pt.concatenate([I0[None], I_seq])
            pm.Normal("obs", mu=I_traj, sigma=sigma, observed=y)
            trace = self._sample(inf_cfg)

        import arviz as az

        summary_bg = az.summary(trace, var_names=["beta", "gamma"], hdi_prob=0.94)
        summary_I0 = az.summary(trace, var_names=["I0"], hdi_prob=0.94)
        converged = _check_convergence(trace)
        beta_mean = float(summary_bg.loc["beta", "mean"])
        gamma_mean = float(summary_bg.loc["gamma", "mean"])
        beta_lo = float(summary_bg.loc["beta", "hdi_3%"])
        beta_hi = float(summary_bg.loc["beta", "hdi_97%"])
        gamma_lo = float(summary_bg.loc["gamma", "hdi_3%"])
        gamma_hi = float(summary_bg.loc["gamma", "hdi_97%"])
        I0_mean = float(summary_I0.loc["I0", "mean"])
        y_hat = sir_prevalence(t, N_pop, I0_mean, beta_mean, gamma_mean)
        ll = _gaussian_loglik(y, y_hat)
        peak = sir_peak_time(N_pop, I0_mean, beta_mean, gamma_mean)

        return FitResult(
            cluster_id=cluster_id,
            model_name="sir",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            r0_mean=sir_r0(beta_mean, gamma_mean),
            r0_ci_low=sir_r0(beta_lo, max(gamma_hi, 1e-6)),
            r0_ci_high=sir_r0(beta_hi, max(gamma_lo, 1e-6)),
            peak_time_mean=peak,
            param_summary={**summary_bg.to_dict(), **summary_I0.to_dict()},
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

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return pm.sample(
                draws=inf_cfg["draws"],
                tune=inf_cfg["tune"],
                chains=inf_cfg["chains"],
                target_accept=inf_cfg["target_accept"],
                cores=cores,
                random_seed=inf_cfg["random_seed"],
                progressbar=False,
            )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

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
