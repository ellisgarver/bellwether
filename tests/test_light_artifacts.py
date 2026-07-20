"""Unit tests for the light-tier artifacts (ADR-083)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from mnd.dashboard.build_artifacts import build_light_artifacts


def _clusters_df() -> pd.DataFrame:
    rows = []
    # Sub-floor cluster 7: three articles over two months in 2023.
    for i, day in enumerate(["2023-03-01", "2023-03-20", "2023-04-18"]):
        rows.append(dict(article_id=f"s{i}", topic=7, chunk_index=0,
                         source_id="bis", url=f"http://x/s{i}",
                         published_at=f"{day}T12:00:00Z",
                         title=f"Repo stress piece {i}",
                         body="repo market stress dealer balance sheets"))
    # Surfaced cluster 0: two articles (stands in for a full-tier neighbour).
    for i, day in enumerate(["2023-03-09", "2023-03-10"]):
        rows.append(dict(article_id=f"a{i}", topic=0, chunk_index=0,
                         source_id="imf", url=f"http://x/a{i}",
                         published_at=f"{day}T12:00:00Z",
                         title=f"Inflation piece {i}", body="inflation prices rising"))
    rows.append(dict(article_id="n1", topic=-1, chunk_index=0, source_id="voxeu",
                     url="http://x/n1", published_at="2021-01-01T12:00:00Z",
                     title="Misc", body="unrelated"))
    return pd.DataFrame(rows)


def _topic_info() -> pd.DataFrame:
    return pd.DataFrame({
        "Topic": [0, 7, -1],
        "Count": [2, 3, 1],
        "Name": ["0_inflation_prices", "7_repo_stress", "-1_noise"],
        "Representation": [["inflation", "prices"], ["repo", "stress"], ["misc"]],
    })


def _adj() -> dict[int, pd.Series]:
    idx7 = pd.date_range("2023-03-01", "2023-04-18", freq="D")
    y7 = np.zeros(len(idx7)); y7[0] = 1.0; y7[19] = 1.0; y7[-1] = 1.0
    idx0 = pd.date_range("2023-03-09", "2023-03-10", freq="D")
    return {7: pd.Series(y7, index=idx7), 0: pd.Series([1.0, 1.0], index=idx0)}


def _cfg() -> dict:
    return {
        "dynamics": {"smoothing_window_days": 7},
        "stages": {"trend_alpha": 0.05, "newly_emerging_recency_weeks": 4,
                   "dormant_peak_fraction": 0.25, "stale_dormant_weeks": 16},
        "display": {"corpus_heating": {"recent_weeks": 16, "baseline_weeks": 52,
                                       "k_sigma": 2.0, "min_articles": 3}},
    }


def test_light_artifact_written_with_weekly_series_and_no_fits(tmp_path):
    centroids = {0: np.array([1.0, 0.0, 0.0]), 7: np.array([0.9, 0.1, 0.0])}
    n = build_light_artifacts(
        [7], _adj(), _clusters_df(), _topic_info(), {7: "G", 0: "E"},
        centroids, {}, _cfg(), tmp_path,
    )
    assert n == 1
    d = json.loads((tmp_path / "narrative_light_7.json").read_text())
    assert d["tier"] == "light"
    assert d["fits"] == [] and d["mediacloud"] is None and d["markets"] is None
    assert d["volume"]["freq"] == "W"
    # weekly grid: 2023-03-01..04-18 spans 8 ISO weeks
    assert 6 <= len(d["volume"]["dates"]) <= 9
    assert d["jel"] == {"code": "G", "in_scope": True}
    assert d["stage"] in {"growth", "stable", "decay", "dormant"}
    assert d["stage_detail"]["trend_slope"] is not None
    assert d["card"]["n_articles"] == 3
    # semantic neighbour: the surfaced cluster 0 is its only candidate
    assert d["similar"]["semantic"] == [0]
    assert d["similar"]["lexical"] == [] and d["similar"]["morphological"] == []


def test_light_artifacts_skip_missing_series(tmp_path):
    n = build_light_artifacts(
        [7, 99], _adj(), _clusters_df(), _topic_info(), {},
        {7: np.ones(3)}, {}, _cfg(), tmp_path,
    )
    assert n == 1  # 99 has no series → skipped, not crashed
