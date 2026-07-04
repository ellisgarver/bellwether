"""Unit tests for the Media Cloud press-heating signal (ADR-064 / ADR-057 §2)."""
from __future__ import annotations

import datetime as dt

from mnd.detection.mediacloud import press_heating


def _series(weeks: int, ratio_fn) -> list[dict]:
    base = dt.date(2023, 1, 1)
    out = []
    for w in range(weeks):
        for d in range(7):
            day = base + dt.timedelta(days=w * 7 + d)
            out.append({"date": day.isoformat(), "ratio": max(ratio_fn(w), 0.0)})
    return out


class TestPressHeating:
    def test_recent_spike_fires(self):
        recs = _series(64, lambda w: 0.001 if w < 60 else 0.010)
        h = press_heating(recs)
        assert h is not None and h["is_heating"] is True
        assert h["z"] >= 2.0
        assert "above its 52-week baseline" in h["caption"]

    def test_flat_series_does_not_fire(self):
        recs = _series(64, lambda w: 0.001)
        h = press_heating(recs)
        assert h is not None and h["is_heating"] is False

    def test_too_short_history_returns_none(self):
        # < recent_weeks + baseline_weeks reliable weeks
        recs = _series(40, lambda w: 0.001)
        assert press_heating(recs) is None

    def test_pre_reliable_years_filtered_out(self):
        base = dt.date(2015, 1, 1)
        recs = [
            {"date": (base + dt.timedelta(days=i)).isoformat(), "ratio": 0.001}
            for i in range(64 * 7)
        ]
        assert press_heating(recs) is None

    def test_zero_variance_baseline_returns_none(self):
        recs = _series(64, lambda w: 0.0)
        assert press_heating(recs) is None

    def test_k_threshold_is_monotone(self):
        # a noisy baseline + a genuine recent bump; is_heating(k) is z >= k, so a
        # lower k can never turn heating off once a higher k has it on.
        import random
        random.seed(1)
        recs = _series(64, lambda w: (0.001 + random.gauss(0, 0.0003)) if w < 60 else 0.003)
        z = press_heating(recs)["z"]
        assert press_heating(recs, k=z - 0.5)["is_heating"] is True
        assert press_heating(recs, k=z + 0.5)["is_heating"] is False
