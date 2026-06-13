"""Unit tests for the Media Cloud press-volume overlay (ADR-042).

These mock the SearchApi so they need neither the `mediacloud` package nor a
live MEDIACLOUD_API_KEY — they validate record mapping, date filtering, ratio
computation, and the no-key guard.
"""
from __future__ import annotations

from datetime import date

import pytest

from mnd.detection.mediacloud import (
    US_NATIONAL_COLLECTION,
    MediaCloudDetector,
)


class _StubSearchApi:
    """Stands in for mediacloud.api.SearchApi."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def story_count_over_time(self, query, start, end, collection_ids=None):
        self.calls.append((query, start, end, tuple(collection_ids or ())))
        return self._rows


def _detector_with(rows):
    det = MediaCloudDetector(api_key="test-key")
    det._search_api = lambda: _StubSearchApi(rows)  # type: ignore[method-assign]
    return det


class TestFetchStoryCounts:
    def test_maps_rows_to_schema(self):
        rows = [
            {"date": "2023-01-01", "count": 10, "total_count": 1000, "ratio": 0.01},
            {"date": date(2023, 1, 2), "count": 20, "total_count": 1000},  # date obj, no ratio
        ]
        det = _detector_with(rows)
        out = list(det.fetch_story_counts("inflation", date(2023, 1, 1), date(2023, 1, 31)))
        assert len(out) == 2
        first = out[0]
        assert first["query"] == "inflation"
        assert first["date"] == "2023-01-01"
        assert first["story_count"] == 10
        assert first["total_count"] == 1000
        assert first["ratio"] == pytest.approx(0.01)
        assert first["collection_ids"] == [US_NATIONAL_COLLECTION]
        assert "retrieved_at" in first

    def test_ratio_computed_when_absent(self):
        rows = [{"date": "2023-01-02", "count": 20, "total_count": 1000}]
        det = _detector_with(rows)
        out = list(det.fetch_story_counts("x", date(2023, 1, 1), date(2023, 1, 31)))
        assert out[0]["ratio"] == pytest.approx(0.02)

    def test_ratio_zero_when_total_zero(self):
        rows = [{"date": "2023-01-02", "count": 0, "total_count": 0}]
        det = _detector_with(rows)
        out = list(det.fetch_story_counts("x", date(2023, 1, 1), date(2023, 1, 31)))
        assert out[0]["ratio"] == 0.0

    def test_filters_out_of_range_and_unparseable_dates(self):
        rows = [
            {"date": "2022-12-31", "count": 5, "total_count": 100},   # before range
            {"date": "2023-02-15", "count": 5, "total_count": 100},   # after range
            {"date": "not-a-date", "count": 5, "total_count": 100},   # junk
            {"date": "2023-01-10", "count": 7, "total_count": 100},   # in range
        ]
        det = _detector_with(rows)
        out = list(det.fetch_story_counts("x", date(2023, 1, 1), date(2023, 1, 31)))
        assert [r["date"] for r in out] == ["2023-01-10"]

    def test_default_collection_is_us_national(self):
        stub = _StubSearchApi([])
        det = MediaCloudDetector(api_key="k")
        det._search_api = lambda: stub  # type: ignore[method-assign]
        list(det.fetch_story_counts("q", date(2023, 1, 1), date(2023, 1, 2)))
        assert stub.calls[0][3] == (US_NATIONAL_COLLECTION,)

    def test_custom_collections_passed_through(self):
        stub = _StubSearchApi([])
        det = MediaCloudDetector(api_key="k")
        det._search_api = lambda: stub  # type: ignore[method-assign]
        list(det.fetch_story_counts("q", date(2023, 1, 1), date(2023, 1, 2), collections=[99]))
        assert stub.calls[0][3] == (99,)

    def test_api_failure_yields_nothing(self):
        det = MediaCloudDetector(api_key="k")

        def _boom():
            raise RuntimeError("network down")

        det._search_api = _boom  # type: ignore[method-assign]
        out = list(det.fetch_story_counts("q", date(2023, 1, 1), date(2023, 1, 2)))
        assert out == []


class TestFromEnv:
    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("MEDIACLOUD_API_KEY", raising=False)
        with pytest.raises(EnvironmentError):
            MediaCloudDetector.from_env()

    def test_present_key_constructs(self, monkeypatch):
        monkeypatch.setenv("MEDIACLOUD_API_KEY", "abc123")
        det = MediaCloudDetector.from_env()
        assert det.api_key == "abc123"


class TestDetectAnomalies:
    def test_flags_spike_above_threshold(self):
        det = MediaCloudDetector(api_key="k")
        baseline = [{"story_count": 10} for _ in range(90)]
        spike = [{"story_count": 1000}]
        out = det.detect_anomalies(baseline + spike, baseline_days=90, threshold_sigma=2.0)
        assert out[-1]["is_anomaly"] is True
        assert out[-1]["z_score"] > 2.0

    def test_too_few_records_no_anomalies(self):
        det = MediaCloudDetector(api_key="k")
        out = det.detect_anomalies([{"story_count": 5}] * 10, baseline_days=90)
        assert all(r["is_anomaly"] is False for r in out)
