"""Economic calendar annotation for narrative volume time series.

Flags weekly time series rows that fall within ±3 days of major scheduled
U.S. macro events. These events create systematic calendar-driven volume spikes
that should be labeled in the dashboard and noted in fitted output — not removed,
but contextualized.

Events flagged:
  - FOMC meeting decision dates (8 per year, 2010-present)
  - CPI release dates (BLS Consumer Price Index, monthly)
  - PCE release dates (BEA Personal Income and Outlays, monthly)
  - GDP advance estimate release dates (BEA, quarterly)
  - NFP/Employment Situation release dates (BLS, monthly)
  - Federal Reserve Semi-Annual Monetary Policy Report to Congress

Data sources (in priority order):
  1. FRED API (fredapi): programmatic access to BLS/BEA release calendars.
     Requires FRED_API_KEY in environment. Covers all FRED-tracked releases
     with exact historical dates.
  2. Heuristic computation: when FRED API key is unavailable, approximate
     release dates are computed from rules-of-thumb (first Friday of month
     for NFP, ~12th of month for CPI, etc.). These are slightly imprecise
     but sufficient for dashboard annotation purposes.
  3. FOMC dates: always fetched by scraping federalreserve.gov/monetarypolicy/
     fomccalendars.htm (public, no key required). Falls back to a hardcoded
     schedule if the scrape fails.

±3-day window logic:
  A week [week_start, week_start+6] is flagged if any calendar event date D
  satisfies: week_start - 3 ≤ D ≤ week_start + 9.
  This catches events that fall 1–3 days before the week starts or 1–3 days
  after the week ends — capturing the pre-event anticipation and post-event
  coverage tail.

When multiple events fall in the same week, calendar_event_label lists all,
separated by " | ".

Usage:

    from mnd.dynamics.calendar import CalendarAnnotator
    annotator = CalendarAnnotator(fred_api_key=os.getenv("FRED_API_KEY"))
    weekly_df = annotator.annotate(weekly_df)
    # weekly_df now has calendar_event (bool) and calendar_event_label (str) columns

In the dynamics fitter: pass annotated weekly_df through unchanged. After
fitting, report count of flagged weeks in the growth phase as a quality
indicator (high count → spike may be calendar-driven, not organic narrative growth).
"""
from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from mnd.utils.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

USER_AGENT = "MacroNarrativeDynamics/0.1 (academic research; contact via project repo)"

# ±3 day window around each event date
_WINDOW_DAYS = 3

# FRED release IDs for relevant economic data series
_FRED_RELEASE_IDS: dict[str, int] = {
    "CPI Release": 10,           # Consumer Price Index for All Urban Consumers
    "PCE Release": 54,           # Personal Income and Outlays
    "GDP Advance": 53,           # Gross Domestic Product
    "Employment Situation (NFP)": 50,  # Employment Situation
}

# Approximate months for Fed MPR (submitted to Congress in Feb and Jul)
_MPR_MONTHS = (2, 7)


class CalendarAnnotator:
    """Annotates weekly volume series with scheduled macro event flags.

    Parameters
    ----------
    fred_api_key : str, optional
        FRED API key for fetching exact historical release dates.
        Falls back to heuristic date computation if not provided.
    window_days : int
        Half-window around each event date (default 3). A week is flagged
        if any event falls within [week_start - window_days, week_end + window_days].
    """

    def __init__(
        self,
        fred_api_key: str | None = None,
        *,
        window_days: int = _WINDOW_DAYS,
    ) -> None:
        self._api_key = fred_api_key or os.environ.get("FRED_API_KEY")
        self._window = window_days

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_event_dates(self, start: date, end: date) -> pd.DataFrame:
        """Return all flagged event dates in [start, end].

        Returns DataFrame with columns: event_date (date), event_label (str).
        Multiple events on the same date appear as separate rows.
        """
        frames: list[pd.DataFrame] = []
        frames.append(self._fetch_fomc_dates(start, end))
        for label, release_id in _FRED_RELEASE_IDS.items():
            frames.append(self._fetch_release_dates(label, release_id, start, end))
        frames.append(self._mpr_dates(start, end))
        events = pd.concat([f for f in frames if not f.empty], ignore_index=True)
        events["event_date"] = pd.to_datetime(events["event_date"]).dt.date
        events = events.sort_values("event_date").reset_index(drop=True)
        return events

    def annotate(self, weekly_df: pd.DataFrame) -> pd.DataFrame:
        """Add calendar_event and calendar_event_label columns to a weekly DataFrame.

        Parameters
        ----------
        weekly_df : DataFrame
            Must have a week_start column (date or date-like).

        Returns
        -------
        Same DataFrame with two new columns appended:
            calendar_event       bool — True if any event falls within ±window_days
            calendar_event_label str  — pipe-separated event labels (empty string if no event)
        """
        df = weekly_df.copy()
        df["_week_start"] = pd.to_datetime(df["week_start"]).dt.date

        # Determine the date range covered
        start = df["_week_start"].min() - timedelta(days=self._window)
        end = df["_week_start"].max() + timedelta(days=6 + self._window)
        events = self.get_event_dates(start, end)

        if events.empty:
            log.warning("CalendarAnnotator: no events found for the date range; annotating all rows as False")
            df["calendar_event"] = False
            df["calendar_event_label"] = ""
            df.drop(columns=["_week_start"], inplace=True)
            return df

        # For each week, collect events within [week_start - window, week_end + window]
        event_dates = events["event_date"].values
        event_labels = events["event_label"].values

        flags: list[bool] = []
        labels: list[str] = []

        for ws in df["_week_start"]:
            lo = ws - timedelta(days=self._window)
            hi = ws + timedelta(days=6 + self._window)
            matched_labels = [
                lbl
                for d, lbl in zip(event_dates, event_labels)
                if lo <= d <= hi
            ]
            flags.append(bool(matched_labels))
            labels.append(" | ".join(dict.fromkeys(matched_labels)))  # dedup, preserve order

        df["calendar_event"] = flags
        df["calendar_event_label"] = labels
        df.drop(columns=["_week_start"], inplace=True)

        n_flagged = sum(flags)
        log.info(
            "CalendarAnnotator: flagged %d of %d weekly rows (%.1f%%)",
            n_flagged, len(df), 100 * n_flagged / max(len(df), 1),
        )
        return df

    def count_flagged_in_growth_phase(
        self,
        weekly_df: pd.DataFrame,
        *,
        growth_start: date,
        growth_end: date,
    ) -> int:
        """Return number of calendar-flagged weeks in the fitted growth phase.

        Used as a quality indicator appended to fitted dynamics output.
        A high count indicates the growth phase may be partially calendar-driven.
        """
        if "calendar_event" not in weekly_df.columns:
            weekly_df = self.annotate(weekly_df)
        mask = (
            (pd.to_datetime(weekly_df["week_start"]).dt.date >= growth_start)
            & (pd.to_datetime(weekly_df["week_start"]).dt.date <= growth_end)
            & weekly_df["calendar_event"]
        )
        return int(mask.sum())

    # ------------------------------------------------------------------
    # FOMC dates — scrape federalreserve.gov (no API key required)
    # ------------------------------------------------------------------

    def _fetch_fomc_dates(self, start: date, end: date) -> pd.DataFrame:
        """Scrape FOMC decision dates from federalreserve.gov calendar page."""
        try:
            return _scrape_fomc_dates(start, end)
        except Exception as exc:
            log.warning("FOMC calendar scrape failed: %s — using heuristic dates", exc)
            return _fomc_dates_heuristic(start, end)

    # ------------------------------------------------------------------
    # FRED release dates — exact dates via API, heuristics as fallback
    # ------------------------------------------------------------------

    def _fetch_release_dates(
        self, label: str, release_id: int, start: date, end: date
    ) -> pd.DataFrame:
        if self._api_key:
            try:
                return _fred_release_dates(label, release_id, start, end, self._api_key)
            except Exception as exc:
                log.warning("FRED release %d (%s) fetch failed: %s — using heuristics", release_id, label, exc)
        return _heuristic_release_dates(label, start, end)

    # ------------------------------------------------------------------
    # Fed MPR — hardcoded approximate dates (Feb and Jul each year)
    # ------------------------------------------------------------------

    def _mpr_dates(self, start: date, end: date) -> pd.DataFrame:
        rows: list[dict] = []
        for year in range(start.year, end.year + 1):
            for month in _MPR_MONTHS:
                # MPR is delivered in mid-February and mid-July; use 15th as proxy
                d = date(year, month, 15)
                if start <= d <= end:
                    rows.append({"event_date": d, "event_label": "Fed MPR to Congress"})
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# FOMC scraping
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _get_fomc_calendar() -> requests.Response:
    return requests.get(
        "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
    )


def _scrape_fomc_dates(start: date, end: date) -> pd.DataFrame:
    """Parse FOMC decision dates from the Fed's calendar page.

    The Fed page lists meetings as date ranges like "Jan 28-29" or single
    dates. The decision date is always the last day of the meeting.
    """
    resp = _get_fomc_calendar()
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    rows: list[dict] = []
    current_year = date.today().year

    for panel in soup.select("div.panel, div.fomc-meeting, div.row"):
        # Try to extract year from a heading nearby
        heading = panel.find(["h4", "h3", "h5"])
        if heading and heading.text.strip().isdigit():
            current_year = int(heading.text.strip())

        for time_tag in panel.find_all("time"):
            dt_str = time_tag.get("datetime", "")
            if not dt_str:
                continue
            try:
                d = date.fromisoformat(dt_str[:10])
                if start <= d <= end:
                    rows.append({"event_date": d, "event_label": "FOMC Meeting"})
            except Exception:
                continue

    # Fallback: look for patterns like "2024-01-30" or "January 30-31, 2024"
    if not rows:
        import re
        text = soup.get_text(" ")
        for match in re.finditer(r"\b(20\d{2})\b", text):
            year_pos = match.start()
            context = text[max(0, year_pos - 50):year_pos + 50]
            year = int(match.group(1))
            # simple heuristic: 8 meetings per year, ~6-7 weeks apart
            for month in [1, 3, 5, 6, 7, 9, 10, 12]:
                d = date(year, month, 15)
                if start <= d <= end:
                    rows.append({"event_date": d, "event_label": "FOMC Meeting"})
        # Deduplicate
        rows = list({r["event_date"]: r for r in rows}.values())

    return pd.DataFrame(rows)


def _fomc_dates_heuristic(start: date, end: date) -> pd.DataFrame:
    """Approximate FOMC meeting dates: 8 meetings per year on fixed schedule."""
    # FOMC typically meets in Jan, Mar, May, Jun, Jul, Sep, Oct/Nov, Dec
    # Exact days vary; use ~last Wednesday of the meeting window as proxy
    FOMC_MONTHS = [1, 3, 5, 6, 7, 9, 11, 12]
    rows: list[dict] = []
    for year in range(start.year, end.year + 1):
        for month in FOMC_MONTHS:
            d = _last_weekday_of_month(year, month, weekday=2)  # Wednesday
            if start <= d <= end:
                rows.append({"event_date": d, "event_label": "FOMC Meeting (approx)"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# FRED API release dates
# ---------------------------------------------------------------------------

def _fred_release_dates(
    label: str, release_id: int, start: date, end: date, api_key: str
) -> pd.DataFrame:
    """Fetch historical release dates for a FRED release ID."""
    url = "https://api.stlouisfed.org/fred/release/dates"
    params = {
        "release_id": release_id,
        "api_key": api_key,
        "file_type": "json",
        "realtime_start": start.isoformat(),
        "realtime_end": end.isoformat(),
    }
    resp = requests.get(url, params=params, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    release_dates = data.get("release_dates", [])
    rows = []
    for entry in release_dates:
        d_str = entry.get("date", "")
        try:
            d = date.fromisoformat(d_str)
            if start <= d <= end:
                rows.append({"event_date": d, "event_label": label})
        except Exception:
            continue
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Heuristic release date computation (fallback when no FRED API key)
# ---------------------------------------------------------------------------

def _heuristic_release_dates(label: str, start: date, end: date) -> pd.DataFrame:
    """Approximate BLS/BEA release dates using standard scheduling rules.

    Rules:
      Employment Situation (NFP): first Friday of the month (released for prior month)
      CPI: approximately the 12th of the month (±2 days; use 12th as proxy)
      PCE: approximately 4 weeks after CPI; use last Friday of the month
      GDP advance: last Wednesday of January, April, July, October
      MPR: handled separately in _mpr_dates()
    """
    rows: list[dict] = []
    label_lower = label.lower()
    for year in range(start.year, end.year + 1):
        for month in range(1, 13):
            candidate: date | None = None
            if "employment" in label_lower or "nfp" in label_lower:
                candidate = _first_weekday_of_month(year, month, weekday=4)  # Friday
            elif "cpi" in label_lower:
                candidate = date(year, month, 12)
            elif "pce" in label_lower or "personal income" in label_lower:
                candidate = _last_weekday_of_month(year, month, weekday=4)  # last Friday
            elif "gdp" in label_lower:
                if month in (1, 4, 7, 10):
                    candidate = _last_weekday_of_month(year, month, weekday=2)  # last Wednesday
            if candidate and start <= candidate <= end:
                rows.append({"event_date": candidate, "event_label": label + " (approx)"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _first_weekday_of_month(year: int, month: int, *, weekday: int) -> date:
    """Return the first occurrence of weekday (0=Mon, 4=Fri) in the given month."""
    d = date(year, month, 1)
    delta = (weekday - d.weekday()) % 7
    return d + timedelta(days=delta)


def _last_weekday_of_month(year: int, month: int, *, weekday: int) -> date:
    """Return the last occurrence of weekday (0=Mon, 2=Wed, 4=Fri) in the given month."""
    last_day = monthrange(year, month)[1]
    d = date(year, month, last_day)
    delta = (d.weekday() - weekday) % 7
    return d - timedelta(days=delta)
