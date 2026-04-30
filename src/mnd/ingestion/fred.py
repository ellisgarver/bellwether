"""FRED (Federal Reserve Economic Data) validation-data fetcher.

This is NOT an article ingestor — it pulls macro time series used to
validate narrative life-cycles against actual macroeconomic outcomes
(plan §10.4). Series IDs below correspond to the validation outcomes
referenced in the project plan.

Requires a free FRED API key set in the FRED_API_KEY environment variable.
Get one at https://fred.stlouisfed.org/docs/api/api_key.html.
"""
from __future__ import annotations

import os
from datetime import date

import pandas as pd

from mnd.utils.logging import get_logger

log = get_logger(__name__)

# Validation series referenced in the project plan §6.2.
DEFAULT_SERIES: dict[str, str] = {
    # Inflation
    "CPIAUCSL": "Headline CPI (seasonally adjusted)",
    "CPILFESL": "Core CPI",
    "PCEPI": "PCE price index",
    "PCEPILFE": "Core PCE",
    "T5YIE": "5-year breakeven inflation",
    "T10YIE": "10-year breakeven inflation",
    "MICH": "Michigan 1-year inflation expectations",
    # Growth & labor
    "GDP": "Gross Domestic Product",
    "GDPC1": "Real GDP",
    "UNRATE": "Unemployment rate",
    "PAYEMS": "Nonfarm payrolls",
    # Yields & rates
    "DGS2": "2-year Treasury yield",
    "DGS10": "10-year Treasury yield",
    "T10Y2Y": "10-2 yield spread",
    "FEDFUNDS": "Effective federal funds rate",
    # Stress
    "VIXCLS": "VIX",
    "BAMLH0A0HYM2": "ICE BofA US High Yield index option-adjusted spread",
    "BAMLC0A0CM": "ICE BofA US Corporate index option-adjusted spread",
    # Sentiment
    "UMCSENT": "U Michigan Consumer Sentiment",
}


class FredFetcher:
    """Wrapper around the fredapi client with retry & series-batch logic."""

    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or os.environ.get("FRED_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "FRED_API_KEY is not set. Get a free key at "
                "https://fred.stlouisfed.org/docs/api/api_key.html and add to .env."
            )
        try:
            from fredapi import Fred
        except ImportError as exc:  # pragma: no cover
            raise ImportError("fredapi is required. `pip install fredapi`.") from exc
        self._fred = Fred(api_key=api_key)

    def fetch(
        self,
        series: dict[str, str] | None = None,
        start: date | str = "2010-01-01",
        end: date | str | None = None,
    ) -> pd.DataFrame:
        """Fetch each series and return a wide DataFrame indexed by date."""
        series = series or DEFAULT_SERIES
        frames = []
        for series_id, label in series.items():
            try:
                s = self._fred.get_series(
                    series_id,
                    observation_start=str(start),
                    observation_end=str(end) if end else None,
                )
                s.name = series_id
                frames.append(s)
            except Exception as exc:  # pragma: no cover
                log.warning("Failed to fetch FRED series %s (%s): %s", series_id, label, exc)
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, axis=1)
        df.index.name = "date"
        return df.sort_index()
