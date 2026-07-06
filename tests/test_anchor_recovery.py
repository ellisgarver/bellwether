"""Anchor recovery criterion (ADR-069): key-term scoping, article folding, noise handling."""
import pandas as pd
import pytest

from mnd.validation.anchor_recovery import validate_anchor_recovery


def _corpus(svb_rows: list[dict]) -> pd.DataFrame:
    """SVB-window rows plus unrelated same-window articles across many clusters."""
    rows = list(svb_rows)
    for i in range(30):
        rows.append(
            {
                "article_id": f"x{i}",
                "topic": i % 9 + 10,
                "title": "unrelated macro topic",
                "body": "gdp outlook",
                "published_at": "2023-03-09",
            }
        )
    return pd.DataFrame(rows)


def test_key_terms_scope_recovery_to_relevant_articles():
    # 5 SVB articles concentrated in one cluster (2 chunks each), 1 outlier.
    svb = []
    for i in range(5):
        svb += [
            {
                "article_id": f"svb{i}",
                "topic": 7,
                "title": "Silicon Valley Bank failure",
                "body": "deposit run FDIC",
                "published_at": "2023-03-10",
            }
        ] * 2
    svb.append(
        {
            "article_id": "svb5",
            "topic": -1,
            "title": "SVB collapse note",
            "body": "bank failure",
            "published_at": "2023-03-11",
        }
    )
    res = validate_anchor_recovery(_corpus(svb), anchor_ids=["anchor_01_svb"])[0]
    # 30 unrelated window articles are excluded; 5/6 matching articles in cluster 7.
    assert res["n_articles"] == 6
    assert res["dominant_cluster"] == 7
    assert res["recovered"] is True


def test_outliers_stay_in_denominator():
    # 2 clustered + 3 outlier SVB articles: best non-noise share is 2/5 < 0.5.
    svb = [
        {"article_id": "a", "topic": 7, "title": "SVB run", "body": "", "published_at": "2023-03-10"},
        {"article_id": "b", "topic": 7, "title": "SVB run", "body": "", "published_at": "2023-03-10"},
        {"article_id": "c", "topic": -1, "title": "SVB run", "body": "", "published_at": "2023-03-10"},
        {"article_id": "d", "topic": -1, "title": "SVB run", "body": "", "published_at": "2023-03-10"},
        {"article_id": "e", "topic": -1, "title": "SVB run", "body": "", "published_at": "2023-03-10"},
    ]
    res = validate_anchor_recovery(_corpus(svb), anchor_ids=["anchor_01_svb"])[0]
    assert res["n_articles"] == 5
    assert res["recovered"] is False
    assert res["concentration"] == pytest.approx(0.4)


def test_no_matching_articles_reports_zero():
    res = validate_anchor_recovery(_corpus([]), anchor_ids=["anchor_01_svb"])[0]
    assert res["n_articles"] == 0
    assert res["recovered"] is False
