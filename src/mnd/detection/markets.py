"""Markets overlay + bidirectional Granger readout (ADR-041).

A reader of a macro narrative wants to know: "did the discourse move before or
after the market did?" This module overlays a free FRED market series (VIX, 10y
yield, equity index, credit spreads) against a narrative's weekly discourse
volume, and — on demand — runs a **bidirectional Granger** test to report which
direction, if any, shows statistically significant temporal precedence.

This is a **display/diagnostic layer only** (ADR-041). Market series NEVER feed
embedding, clustering, or dynamics fitting — the overlay is computed after the
corpus is built, so the no-paid-dep core invariant and ADR-020 (no external
signal into clustering) are untouched. FRED is free.

Granger precedence is temporal ordering, NOT causation. Every readout carries
the caption "this shows timing, not cause" (feedback_frontend_clarity) so the UI
cannot mis-educate. The prior Bloomberg CPI-surprise control (paid, removed
source per ADR-010) is intentionally dropped.
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

from mnd.utils.logging import get_logger

log = get_logger(__name__)

TIMING_NOT_CAUSE = "This shows timing, not cause."

# Friendly handle → FRED series id. All free daily series already in FRED's
# DEFAULT_SERIES (mnd.ingestion.fred); kept here so the overlay's choices are
# self-documenting and the UI can offer a short menu.
MARKET_SERIES: dict[str, str] = {
    "vix": "VIXCLS",                 # equity-volatility / stress
    "10y_yield": "DGS10",            # 10-year Treasury yield
    "2y_yield": "DGS2",              # 2-year Treasury yield
    "yield_spread": "T10Y2Y",        # 10y-2y spread (recession watch)
    "hy_spread": "BAMLH0A0HYM2",     # high-yield credit spread
    "ig_spread": "BAMLC0A0CM",       # investment-grade credit spread
}

# Granger needs a few cycles of slack beyond the lag order to be meaningful.
_MIN_OBS_PER_LAG = 5


class MarketsOverlay:
    """Build the weekly markets-vs-discourse overlay and the Granger readout.

    Usage:
        overlay = MarketsOverlay.from_env()
        df = overlay.build_overlay(narrative_daily_volume, series="vix")
        readout = overlay.granger_bidirectional(df)

    ``fred`` may be any object exposing ``.fetch(series=..., start=, end=)`` and
    returning a wide date-indexed DataFrame (so tests can inject a stub without a
    live FRED key).
    """

    def __init__(self, fred: Any | None = None) -> None:
        self._fred = fred

    @classmethod
    def from_env(cls) -> "MarketsOverlay":
        from mnd.ingestion.fred import FredFetcher

        return cls(fred=FredFetcher())

    # ------------------------------------------------------------------
    # Overlay construction
    # ------------------------------------------------------------------

    @staticmethod
    def weekly_volume(daily_volume: pd.Series) -> pd.Series:
        """Resample a daily discourse-volume series to weekly totals (W-SUN)."""
        s = daily_volume.copy()
        s.index = pd.to_datetime(s.index)
        weekly = s.resample("W").sum()
        weekly.name = "volume"
        return weekly

    def _resolve_series_id(self, series: str) -> str:
        return MARKET_SERIES.get(series, series)

    def build_overlay(
        self, daily_volume: pd.Series, series: str = "vix"
    ) -> pd.DataFrame:
        """Return a weekly ``[volume, market]`` DataFrame aligned on a common index.

        The market series is fetched over the narrative's own date span and
        resampled to the weekly mean (markets are a level, not a count). Rows
        where either column is missing are dropped so Granger sees a clean,
        gap-free pair.
        """
        if self._fred is None:
            raise ValueError("No FRED client configured; use MarketsOverlay.from_env().")

        weekly = self.weekly_volume(daily_volume)
        if weekly.empty:
            return pd.DataFrame(columns=["volume", "market"])

        series_id = self._resolve_series_id(series)
        start = weekly.index.min().date()
        end = weekly.index.max().date()

        raw = self._fred.fetch(series={series_id: series_id}, start=start, end=end)
        if raw is None or raw.empty or series_id not in raw.columns:
            log.warning("Markets overlay: FRED returned no data for %s", series_id)
            out = weekly.to_frame()
            out["market"] = np.nan
            return out

        market = raw[series_id].copy()
        market.index = pd.to_datetime(market.index)
        market_weekly = market.resample("W").mean()
        market_weekly.name = "market"

        out = pd.concat([weekly, market_weekly], axis=1).dropna()
        out.attrs["series_id"] = series_id
        out.attrs["series_label"] = series
        return out

    # ------------------------------------------------------------------
    # Bidirectional Granger
    # ------------------------------------------------------------------

    def granger_bidirectional(
        self,
        overlay: pd.DataFrame,
        *,
        max_lag: int = 4,
        alpha: float = 0.05,
    ) -> dict[str, Any]:
        """Run bidirectional Granger on the first-differenced overlay.

        Tests both ``volume → market`` and ``market → volume`` and reports the
        most significant lag in each direction, plus a plain-English verdict.
        First-differencing handles the non-stationarity Granger requires
        (ADR-041). Returns a dict that always carries the timing-not-cause
        caption; on insufficient data it reports ``verdict="insufficient data"``
        rather than raising.
        """
        result: dict[str, Any] = {
            "series_id": overlay.attrs.get("series_id"),
            "series_label": overlay.attrs.get("series_label"),
            "max_lag": max_lag,
            "alpha": alpha,
            "caption": TIMING_NOT_CAUSE,
        }

        clean = overlay[["volume", "market"]].dropna()
        diffed = clean.diff().dropna()
        n = len(diffed)
        result["n_obs"] = n

        if n < _MIN_OBS_PER_LAG * max_lag:
            result["verdict"] = "insufficient data"
            result["volume_leads_market"] = None
            result["market_leads_volume"] = None
            return result

        vol = diffed["volume"].to_numpy()
        mkt = diffed["market"].to_numpy()

        # grangercausalitytests(data[:, [a, b]]) tests whether b Granger-causes a.
        v_leads_m = self._best_lag(np.column_stack([mkt, vol]), max_lag)  # vol → mkt
        m_leads_v = self._best_lag(np.column_stack([vol, mkt]), max_lag)  # mkt → vol
        for d in (v_leads_m, m_leads_v):
            d["significant"] = (d.get("min_p") or 1.0) < alpha

        result["volume_leads_market"] = v_leads_m
        result["market_leads_volume"] = m_leads_v
        result["verdict"] = self._verdict(v_leads_m, m_leads_v, alpha)
        return result

    @staticmethod
    def _best_lag(data: np.ndarray, max_lag: int) -> dict[str, Any]:
        """Smallest ssr-F p-value across lags 1..max_lag and the lag achieving it."""
        from statsmodels.tsa.stattools import grangercausalitytests

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                res = grangercausalitytests(data, maxlag=max_lag, verbose=False)
            except Exception as exc:  # singular matrix, etc.
                log.warning("Granger test failed: %s", exc)
                return {"min_p": None, "best_lag": None, "significant": False}

        best_lag, best_p = None, np.inf
        for lag, (stats, _) in res.items():
            p = stats["ssr_ftest"][1]
            if p < best_p:
                best_p, best_lag = p, lag
        return {"min_p": float(best_p), "best_lag": int(best_lag)}

    @staticmethod
    def _verdict(
        v_leads_m: dict[str, Any], m_leads_v: dict[str, Any], alpha: float
    ) -> str:
        vm = (v_leads_m.get("min_p") or 1.0) < alpha
        mv = (m_leads_v.get("min_p") or 1.0) < alpha
        if vm and mv:
            return "bidirectional precedence"
        if vm:
            return "discourse precedes market"
        if mv:
            return "market precedes discourse"
        return "no significant precedence"
