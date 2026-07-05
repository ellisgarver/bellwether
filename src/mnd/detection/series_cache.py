"""Delta-fetch cache for external daily time series (ADR-068).

Both display overlays pull a daily series that is stable in its history but
mutable near the frontier — Media Cloud indexes with a lag (recent days are
revised), FRED revises. Caching must therefore be **correct first**: never serve
stale recent data. This cache reuses only settled history and always re-fetches
the recent ``refetch_days`` window (plus any range the cache does not yet cover),
merging so fresh values overwrite cached ones. A series fully covered by cache and
ending far before ``today`` triggers no fetch at all.

The cache is content-addressed by the series' identity (a Media Cloud query, a FRED
series id) and stored as JSON. Deleting a cache file forces a clean refetch.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any, Callable


def cache_key(identity: str) -> str:
    """Stable filename-safe key for a series identity (query string, series id)."""
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]


def _d(s: str) -> _dt.date:
    return _dt.date.fromisoformat(str(s)[:10])


def merge_by_date(cached: list[dict], fresh: list[dict], date_key: str = "date") -> list[dict]:
    """Merge two record lists by day; ``fresh`` overwrites ``cached``. Sorted."""
    by_day: dict[str, dict] = {str(r[date_key])[:10]: r for r in cached}
    for r in fresh:  # fresh (re-fetched recent window) wins
        by_day[str(r[date_key])[:10]] = r
    return [by_day[d] for d in sorted(by_day)]


def fetch_ranges(
    cached_dates: list[str],
    start: str,
    end: str,
    refetch_days: int,
    today: str,
) -> list[tuple[str, str]]:
    """Inclusive [start, end] date ranges still to fetch given cached coverage.

    - No cache → the whole request.
    - A **head gap** (request starts before cached history) is fetched.
    - The **recent window** ``[min(cached_max, end) − refetch_days, end]`` is fetched
      whenever the cache does not already reach ``end`` OR ``end`` is within
      ``refetch_days`` of ``today`` (i.e. the series is still mutable there). A dead
      series fully covered and ending well before today needs nothing.
    """
    if not cached_dates:
        return [(start, end)]
    cmin, cmax = cached_dates[0], cached_dates[-1]
    ranges: list[tuple[str, str]] = []
    if _d(start) < _d(cmin):
        ranges.append((start, (_d(cmin) - _dt.timedelta(days=1)).isoformat()))
    mutable = _d(end) >= _d(today) - _dt.timedelta(days=refetch_days)
    if _d(cmax) < _d(end) or mutable:
        anchor = min(_d(cmax), _d(end))
        tail_start = max(_d(start), anchor - _dt.timedelta(days=refetch_days))
        if tail_start <= _d(end):
            ranges.append((tail_start.isoformat(), end))
    return ranges


def delta_fetch(
    fetch_fn: Callable[[str, str], list[dict]],
    cache_path: Path,
    start: str,
    end: str,
    *,
    refetch_days: int,
    today: str | None = None,
    date_key: str = "date",
) -> list[dict]:
    """Return the daily records for [start, end], fetching only what's needed (ADR-068).

    ``fetch_fn(sub_start, sub_end) -> list[dict]`` performs a real fetch for a
    sub-range. The merged series is persisted; only records within [start, end] are
    returned (callers slice per narrative).
    """
    today = today or _dt.date.today().isoformat()
    cached: list[dict] = []
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8")).get("records", [])
        except Exception:  # corrupt — treat as cold
            cached = []

    cached_dates = sorted(str(r[date_key])[:10] for r in cached)
    fresh: list[dict] = []
    for a, b in fetch_ranges(cached_dates, start, end, refetch_days, today):
        fresh.extend(fetch_fn(a, b))

    merged = merge_by_date(cached, fresh, date_key=date_key) if (fresh or cached) else []
    if fresh:  # only rewrite when something was fetched
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"records": merged, "fetched_through": end}),
            encoding="utf-8",
        )
    lo, hi = str(start)[:10], str(end)[:10]
    return [r for r in merged if lo <= str(r[date_key])[:10] <= hi]
