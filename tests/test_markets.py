"""Unit tests for the markets overlay + bidirectional Granger readout (ADR-041).

These inject a stub FRED client, so they need neither the `fredapi` package nor
a live FRED_API_KEY — they validate weekly resampling, overlay alignment,
Granger direction/verdict, the insufficient-data guard, and that every readout
carries the timing-not-cause caption.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mnd.detection.markets import (
    MARKET_SERIES,
    TIMING_NOT_CAUSE,
    MarketsOverlay,
)


class _StubFred:
    """Returns a preset wide DataFrame regardless of the requested span."""

    def __init__(self, frame: pd.DataFrame):
        self._frame = frame
        self.calls = []

    def fetch(self, series=None, start=None, end=None):
        self.calls.append((series, start, end))
        return self._frame


def _daily_volume(days: int = 140, start="2023-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=days, freq="D")
    return pd.Series(np.arange(days, dtype=float), index=idx, name="volume")


class TestWeeklyVolume:
    def test_resamples_daily_to_weekly_sum(self):
        idx = pd.date_range("2023-01-02", periods=14, freq="D")  # Mon start
        s = pd.Series(np.ones(14), index=idx)
        weekly = MarketsOverlay.weekly_volume(s)
        assert weekly.sum() == pytest.approx(14.0)
        assert weekly.name == "volume"
        assert isinstance(weekly.index, pd.DatetimeIndex)


class TestBuildOverlay:
    def test_aligns_volume_and_market(self):
        vol = _daily_volume()
        market_idx = pd.date_range("2023-01-01", periods=140, freq="D")
        fred_frame = pd.DataFrame(
            {"VIXCLS": np.linspace(15.0, 30.0, 140)}, index=market_idx
        )
        overlay = MarketsOverlay(fred=_StubFred(fred_frame))
        df = overlay.build_overlay(vol, series="vix")
        assert list(df.columns) == ["volume", "market"]
        assert not df.empty
        assert df["market"].notna().all()
        assert df.attrs["series_id"] == "VIXCLS"

    def test_friendly_handle_resolves_to_fred_id(self):
        vol = _daily_volume(days=30)
        stub = _StubFred(pd.DataFrame())
        overlay = MarketsOverlay(fred=stub)
        overlay.build_overlay(vol, series="vix")
        # The fetch call must request the resolved FRED id, not the handle.
        requested = list(stub.calls[0][0].keys())
        assert requested == [MARKET_SERIES["vix"]]

    def test_raw_fred_id_passthrough(self):
        vol = _daily_volume(days=30)
        stub = _StubFred(pd.DataFrame())
        overlay = MarketsOverlay(fred=stub)
        overlay.build_overlay(vol, series="DGS10")
        assert list(stub.calls[0][0].keys()) == ["DGS10"]

    def test_missing_market_data_yields_nan_column(self):
        vol = _daily_volume(days=30)
        overlay = MarketsOverlay(fred=_StubFred(pd.DataFrame()))
        df = overlay.build_overlay(vol, series="vix")
        assert "market" in df.columns
        assert df["market"].isna().all()

    def test_no_fred_client_raises(self):
        overlay = MarketsOverlay(fred=None)
        with pytest.raises(ValueError):
            overlay.build_overlay(_daily_volume(days=10))


class TestGrangerBidirectional:
    def _causal_overlay(self, n=120, seed=0):
        """market[t] ≈ 0.8 * volume[t-1] → discourse should precede market."""
        rng = np.random.default_rng(seed)
        idx = pd.date_range("2023-01-01", periods=n, freq="W")
        vol = rng.normal(size=n).cumsum()
        mkt = np.empty(n)
        mkt[0] = 0.0
        for t in range(1, n):
            mkt[t] = 0.8 * vol[t - 1] + rng.normal(scale=0.5)
        return pd.DataFrame({"volume": vol, "market": mkt}, index=idx)

    def test_discourse_precedes_market(self):
        overlay = MarketsOverlay(fred=None)
        out = overlay.granger_bidirectional(self._causal_overlay(), max_lag=3)
        assert out["verdict"] == "discourse precedes market"
        assert out["volume_leads_market"]["significant"] is True
        assert out["market_leads_volume"]["significant"] is False

    def test_caption_always_present(self):
        overlay = MarketsOverlay(fred=None)
        out = overlay.granger_bidirectional(self._causal_overlay(), max_lag=3)
        assert out["caption"] == TIMING_NOT_CAUSE

    def test_insufficient_data_guarded(self):
        overlay = MarketsOverlay(fred=None)
        idx = pd.date_range("2023-01-01", periods=6, freq="W")
        df = pd.DataFrame(
            {"volume": np.arange(6.0), "market": np.arange(6.0)}, index=idx
        )
        out = overlay.granger_bidirectional(df, max_lag=4)
        assert out["verdict"] == "insufficient data"
        assert out["volume_leads_market"] is None
        assert out["caption"] == TIMING_NOT_CAUSE

    def test_significant_flag_set_from_alpha(self):
        overlay = MarketsOverlay(fred=None)
        out = overlay.granger_bidirectional(
            self._causal_overlay(), max_lag=3, alpha=0.05
        )
        d = out["volume_leads_market"]
        assert (d["min_p"] < 0.05) == d["significant"]
