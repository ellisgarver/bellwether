"""Correctness tests for the delta-fetch series cache (ADR-068).

The load-bearing property: the cache must never miss a data change. It reuses only
settled history and always re-fetches the recent/mutable window.
"""
from __future__ import annotations

from mnd.detection.series_cache import delta_fetch, fetch_ranges, merge_by_date


def _recs(dates, val=1):
    return [{"date": d, "story_count": val} for d in dates]


class TestFetchRanges:
    def test_no_cache_fetches_everything(self):
        assert fetch_ranges([], "2023-01-01", "2023-01-10", 7, "2026-07-05") == [
            ("2023-01-01", "2023-01-10")
        ]

    def test_dead_series_fully_cached_needs_no_fetch(self):
        # cache covers the whole request and end is long before today → nothing.
        cached = [f"2020-06-{d:02d}" for d in range(1, 21)]
        assert fetch_ranges(cached, "2020-06-01", "2020-06-20", 7, "2026-07-05") == []

    def test_live_series_refetches_recent_window(self):
        # end is near today → re-fetch the trailing refetch_days even if cached.
        cached = [f"2026-06-{d:02d}" for d in range(1, 31)]
        r = fetch_ranges(cached, "2026-06-01", "2026-06-30", 7, "2026-07-02")
        assert r == [("2026-06-23", "2026-06-30")]  # last 7 days re-fetched

    def test_new_data_beyond_cache_is_fetched(self):
        cached = [f"2026-06-{d:02d}" for d in range(1, 21)]  # through 06-20
        r = fetch_ranges(cached, "2026-06-01", "2026-06-30", 7, "2026-07-02")
        # tail anchored at cached_max(06-20)-7 = 06-13 → covers the gap + recent
        assert r == [("2026-06-13", "2026-06-30")]

    def test_head_gap_is_backfilled(self):
        cached = [f"2026-06-{d:02d}" for d in range(10, 21)]  # 06-10..06-20
        r = fetch_ranges(cached, "2026-06-01", "2026-06-20", 7, "2026-07-05")
        assert ("2026-06-01", "2026-06-09") in r  # head backfilled


class TestMerge:
    def test_fresh_overwrites_cached_for_same_day(self):
        cached = [{"date": "2026-06-01", "story_count": 5}]
        fresh = [{"date": "2026-06-01", "story_count": 9}]  # a revision
        assert merge_by_date(cached, fresh) == [{"date": "2026-06-01", "story_count": 9}]


class TestDeltaFetch:
    def test_cold_then_warm_reuses_and_captures_new(self, tmp_path):
        calls = []

        def fetch_fn(a, b):
            calls.append((a, b))
            # produce one record per day in [a, b]
            import datetime as dt
            d0, d1 = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
            out, d = [], d0
            while d <= d1:
                out.append({"date": d.isoformat(), "story_count": 1})
                d += dt.timedelta(days=1)
            return out

        cache = tmp_path / "s.json"
        # Cold: fetch the whole span.
        r1 = delta_fetch(fetch_fn, cache, "2026-06-01", "2026-06-20",
                         refetch_days=7, today="2026-06-20")
        assert len(r1) == 20 and calls == [("2026-06-01", "2026-06-20")]

        # Warm, a week later: only the recent window + new days are fetched.
        calls.clear()
        r2 = delta_fetch(fetch_fn, cache, "2026-06-01", "2026-06-27",
                         refetch_days=7, today="2026-06-27")
        assert len(r2) == 27                       # full series returned
        assert len(calls) == 1                     # one delta fetch, not a full refetch
        a, b = calls[0]
        assert a >= "2026-06-13" and b == "2026-06-27"   # recent window only

    def test_returns_only_requested_window(self, tmp_path):
        def fetch_fn(a, b):
            return _recs(["2026-06-05", "2026-06-06", "2026-06-07"])
        cache = tmp_path / "s.json"
        r = delta_fetch(fetch_fn, cache, "2026-06-06", "2026-06-06",
                        refetch_days=7, today="2026-06-06")
        assert [x["date"] for x in r] == ["2026-06-06"]
