"""Bayesian dynamics fitting with PyMC.

Fits every configured lens (logistic, SIR, Bass) to a cluster's daily
article-count series and returns them all side by side; AICc is a displayed
diagnostic on each FitResult, not a selection gate. Model-free shape-facts are
computed alongside.

Stage classification no longer keys off these fits; stage is a model-free trend
test. The fits are display lenses. `staging_fit` is retained only to surface a
representative R_0 headline -- the SIR fit when it converged, else the logistic
fit -- as the "was it contagious?" SIR-lens value. Bass has no R_0 (its headline
is the innovation/imitation balance).

SIR model: uses a pytensor.scan discrete-time Euler loop so the ODE is
differentiable through PyMC's NUTS sampler without an external ODE solver. The
scan cost is O(series length), so the SIR fit runs on a weekly grid (ADR-053);
the fitted per-week rates are converted to per-day for the displayed daily curve
and peak time, and R_0 = beta/gamma is grid-invariant.

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
    logistic_r0,
    shape_facts,
    sir_peak_time,
    sir_prevalence,
    sir_r0,
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
    r0_mean: float | None = None
    r0_median: float | None = None
    r0_ci_low: float | None = None
    r0_ci_high: float | None = None
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
        """Fit every configured lens; return all side by side (ADR-039)."""
        smoothed = self.smooth_series(daily_counts)
        n = len(smoothed)
        t = np.arange(n, dtype=float)
        y = smoothed.values.astype(float)

        # Fit the lenses on the central-mass window (ADR-060): drop the sparse
        # leading/trailing stragglers that otherwise stretch nearly every fit series
        # to ~14 years and destabilise the SIR ODE scan. The window carries the full
        # active lifecycle (all waves that hold real attention); only negligible-mass
        # tails are trimmed. Each fitted curve is reprojected back onto the full daily
        # grid for display, and shape-facts + staging stay on the full series.
        alpha = float(self._cfg["dynamics"].get("fit_window_mass_alpha", 0.05))
        i0, i1 = _trim_window_central_mass(y, alpha)
        t_win = np.arange(i1 - i0 + 1, dtype=float)
        y_win = y[i0:i1 + 1]

        all_fits: list[FitResult] = []
        for model_name in self._cfg["dynamics"]["models_to_fit"]:
            log.info("Cluster %s — fitting %s on window [%d:%d] of %d", cluster_id, model_name, i0, i1, n)
            fit = self._fit_model(cluster_id, model_name, t_win, y_win)
            all_fits.append(_reproject_to_full(fit, i0, n))

        staging = self._select_staging_fit(cluster_id, all_fits)
        facts = shape_facts(t, y)

        log.info(
            "Cluster %s staging: %s (R0=%s, converged=%s); waves=%s",
            cluster_id,
            staging.model_name,
            f"{staging.r0_mean:.2f}" if staging.r0_mean is not None else "n/a",
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

    @staticmethod
    def _select_staging_fit(
        cluster_id: int | str, all_fits: list[FitResult]
    ) -> FitResult:
        """Pick the fit whose R_0 headline is displayed (display only).

        Prefer the converged SIR fit (its beta/gamma R_0 is the genuine "was it
        contagious?" value), else the converged logistic fit, else any fit. This
        no longer decides the stage; that is the model-free trend test.
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
        gamma_prior = self._cfg["dynamics"]["priors"]["sir"]["gamma_mean"]
        k_mean = float(summary.loc["k", "mean"])
        k_lo = float(summary.loc["k", "hdi_3%"])
        k_hi = float(summary.loc["k", "hdi_97%"])
        L_mean = float(summary.loc["L", "mean"])
        t0_mean = float(summary.loc["t0", "mean"])
        # logistic_r0 is monotonic in k, so the median commutes through it.
        k_median = float(np.median(np.asarray(trace.posterior["k"]).reshape(-1)))
        curve = logistic(t, L_mean, k_mean, t0_mean)
        ll = _gaussian_loglik(y, curve)

        return FitResult(
            cluster_id=cluster_id,
            model_name="logistic",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            r0_mean=logistic_r0(k_mean, gamma_prior),
            r0_median=logistic_r0(k_median, gamma_prior),
            r0_ci_low=logistic_r0(k_lo, gamma_prior),
            r0_ci_high=logistic_r0(k_hi, gamma_prior),
            peak_time_mean=t0_mean,
            peak_time_ci_low=float(summary.loc["t0", "hdi_3%"]),
            peak_time_ci_high=float(summary.loc["t0", "hdi_97%"]),
            param_summary=summary.to_dict(),
            curve=[float(v) for v in curve],
        )

    # ------------------------------------------------------------------
    # SIR — discrete-time Euler via pytensor.scan (differentiable)
    # ------------------------------------------------------------------

    def _fit_sir(
        self, cluster_id: int | str, t: np.ndarray, y: np.ndarray
    ) -> FitResult:
        import pymc as pm
        import pytensor
        import pytensor.tensor as pt

        priors = self._cfg["dynamics"]["priors"]["sir"]
        inf_cfg = self._cfg["dynamics"]["sir_inference"]
        base_grid = int(self._cfg["dynamics"]["sir_fit_grid_days"])
        max_steps = int(self._cfg["dynamics"].get("sir_max_grid_steps", 200))
        # N_pop is the daily total, so the population scale is grid-invariant. The
        # scan runs on a coarsened grid to keep its O(T) cost bounded: grid is chosen
        # so the Euler scan is at most `sir_max_grid_steps` long regardless of the
        # window's length (ADR-060), then binned. Binning averages rather than sums,
        # so y_fit and the priors keyed to it stay on the daily amplitude.
        grid = max(base_grid, int(np.ceil(len(y) / max(max_steps, 1))))
        N_pop = float(max(y.sum() * 2.0, 100.0))
        y_fit, eff_grid = _bin_to_grid(y, grid)
        T = len(y_fit)

        with pm.Model():
            # LogNormal keeps both rates strictly positive (ADR-060): the prior HalfNormal
            # put mass at gamma->0, exploding R_0 = beta/gamma and the Euler scan.
            beta = pm.LogNormal("beta", mu=float(np.log(priors["beta_mean"])), sigma=priors["beta_log_sd"])
            gamma = pm.LogNormal("gamma", mu=float(np.log(priors["gamma_mean"])), sigma=priors["gamma_log_sd"])
            I0 = pm.HalfNormal("I0", sigma=max(float(y_fit[:5].mean()), 1.0) * 3)
            sigma = pm.HalfNormal("sigma", sigma=float(y_fit.std() + 1.0))

            S_init = pt.as_tensor_variable(N_pop) - I0
            R_init = pt.zeros(())

            def sir_step(S_prev, I_prev, R_prev, b, g, n):
                new_inf = pt.clip(b * S_prev * I_prev / n, 0.0, S_prev)
                rec = pt.clip(g * I_prev, 0.0, I_prev)
                return S_prev - new_inf, I_prev + new_inf - rec, R_prev + rec

            (_, I_seq, _), _ = pytensor.scan(
                sir_step,
                outputs_info=[S_init, I0, R_init],
                non_sequences=[beta, gamma, pt.as_tensor_variable(N_pop)],
                n_steps=T - 1,
            )
            I_traj = pt.concatenate([I0[None], I_seq])
            pm.Normal("obs", mu=I_traj, sigma=sigma, observed=y_fit)
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
        # R0=beta/gamma is a ratio, so median(R0) needs the per-draw ratio,
        # not the ratio of the marginal medians.
        beta_draws = np.asarray(trace.posterior["beta"]).reshape(-1)
        gamma_draws = np.clip(np.asarray(trace.posterior["gamma"]).reshape(-1), 1e-6, None)
        r0_median = float(np.median(beta_draws / gamma_draws))
        # beta/gamma are per-grid-step rates. R_0 = beta/gamma is dimensionless,
        # so it is reported directly from the posterior (the grid factor cancels).
        # The displayed curve and peak carry time units, so convert to per-day
        # before integrating on the daily grid t (ADR-053).
        beta_day = beta_mean / eff_grid
        gamma_day = gamma_mean / eff_grid
        y_hat = sir_prevalence(t, N_pop, I0_mean, beta_day, gamma_day)
        ll = _gaussian_loglik(y, y_hat)
        peak = sir_peak_time(N_pop, I0_mean, beta_day, gamma_day)

        return FitResult(
            cluster_id=cluster_id,
            model_name="sir",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            r0_mean=sir_r0(beta_mean, gamma_mean),
            r0_median=r0_median,
            r0_ci_low=sir_r0(beta_lo, max(gamma_hi, 1e-6)),
            r0_ci_high=sir_r0(beta_hi, max(gamma_lo, 1e-6)),
            peak_time_mean=peak,
            param_summary={**summary_bg.to_dict(), **summary_I0.to_dict()},
            curve=[float(v) for v in y_hat],
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

        # Bass has no R_0; its headline is the innovation/imitation balance.
        return FitResult(
            cluster_id=cluster_id,
            model_name="bass",
            converged=converged,
            aicc=aicc(ll, k=3, n=len(y)),
            r0_mean=None,
            peak_time_mean=bass_peak_time(p_mean, q_mean),
            param_summary={
                **summary.to_dict(),
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

def _bin_to_grid(y: np.ndarray, grid: int) -> tuple[np.ndarray, int]:
    """Block-average a daily series onto a coarser grid for the SIR fit (ADR-053).

    The SIR scan cost is O(len(y)); binning the already-7-day-smoothed daily
    series onto a weekly grid shortens the scan ~``grid``-fold. Averaging (not
    summing) preserves the daily amplitude, so N_pop, the priors, and the fitted
    I0 stay on daily units and the per-grid-step rates convert back to per-day by
    dividing by the returned factor. Returns the series and the grid factor
    actually applied (1 when no binning happened). Series shorter than four
    grid-steps are already cheap and are returned unchanged on the daily grid.
    """
    y = np.asarray(y, dtype=float)
    grid = max(int(grid), 1)
    if grid == 1 or len(y) < 4 * grid:
        return y, 1
    n_bins = int(np.ceil(len(y) / grid))
    binned = np.array(
        [float(y[i * grid : (i + 1) * grid].mean()) for i in range(n_bins)],
        dtype=float,
    )
    return binned, grid


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
