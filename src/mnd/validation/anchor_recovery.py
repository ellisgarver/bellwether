"""Anchor narrative recovery validation (ADR-019, criterion per ADR-069).

For each anchor, collects the articles published within its reference window
whose title or body matches any of the anchor's fixed ``key_terms`` (from the
Phase-0 anchor registry), folds chunks to articles (majority topic per
``article_id``), and checks whether >=50% of those articles fall in a single
non-noise cluster. Outlier-assigned articles stay in the denominator, so heavy
outlier assignment still costs recovery.

Recovery is reported as a rate, not as a pass/fail gate. Anchor recovery is a
diagnostic quality signal, and no parameter is tuned toward it (ADR-040).

Configuration: config.validation.anchor_tolerance_days.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from mnd.utils.config import load_config, project_root
from mnd.utils.logging import get_logger

log = get_logger(__name__)

# Fraction of anchor articles that must fall in one cluster to count as recovered
_RECOVERY_CONCENTRATION = 0.50


def _load_anchors(anchor_ids: list[str] | None = None) -> list[dict[str, Any]]:
    path = project_root() / "data" / "anchors" / "anchor_narratives.jsonl"
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if anchor_ids:
        records = [r for r in records if r["id"] in anchor_ids]
    return records


def _find_anchor_articles(
    df: pd.DataFrame,
    anchor: dict[str, Any],
    tolerance_days: int,
) -> pd.DataFrame:
    """Rows in the anchor window whose text matches the anchor's key terms.

    The window alone is not a relevance filter on the full-breadth corpus
    (ADR-020) — the basis set publishes across all of macro every week — so the
    rows are additionally restricted to those whose title or body contains any
    of the anchor's fixed ``key_terms`` (case-insensitive substring, ADR-069).
    """
    if "published_at" not in df.columns:
        return df.iloc[0:0]

    dates = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    ref_start = pd.Timestamp(anchor["reference_window_start"], tz="UTC")
    ref_end = pd.Timestamp(anchor["reference_window_end"], tz="UTC")
    tol = pd.Timedelta(days=tolerance_days)
    window = df[(dates >= ref_start - tol) & (dates <= ref_end + tol)]

    terms = [str(t).lower() for t in anchor.get("key_terms", []) if str(t).strip()]
    if not terms or window.empty:
        return window

    text = pd.Series("", index=window.index)
    for col in ("title", "body"):
        if col in window.columns:
            text = text + " " + window[col].fillna("").astype(str).str.lower()
    mask = pd.Series(False, index=window.index)
    for t in terms:
        mask |= text.str.contains(t, regex=False)
    return window[mask]


def _check_recovery(
    anchor_df: pd.DataFrame,
    anchor: dict[str, Any],
) -> dict[str, Any]:
    """Compute recovery metrics for one anchor (article-level, ADR-069)."""
    if "topic" in anchor_df.columns:
        cluster_col = "topic"
    elif "topic_medium" in anchor_df.columns:
        cluster_col = "topic_medium"
    elif "topic_fine" in anchor_df.columns:
        cluster_col = "topic_fine"
    else:
        raise KeyError(
            "anchor recovery: clustered DataFrame has no 'topic' column "
            "(expected ADR-019 single-granularity column)"
        )

    # Chunks fold to articles: an article's cluster is the majority topic among
    # its chunks (ties break to the lowest topic id, deterministic).
    if "article_id" in anchor_df.columns and not anchor_df.empty:
        article_topics = (
            anchor_df.groupby("article_id")[cluster_col]
            .agg(lambda s: int(s.value_counts().index[0]))
        )
    else:
        article_topics = anchor_df[cluster_col].astype(int)

    n = len(article_topics)
    if n == 0:
        return {
            "anchor_id": anchor["id"],
            "recovered": False,
            "n_articles": 0,
            "dominant_cluster": None,
            "concentration": 0.0,
            "note": "no matching articles in the reference window",
        }

    # Largest single non-noise cluster share; outlier-assigned articles stay in
    # the denominator, so heavy outlier assignment still costs recovery.
    counts = article_topics[article_topics >= 0].value_counts()
    if counts.empty:
        dominant: int | None = None
        concentration = 0.0
    else:
        dominant = int(counts.index[0])
        concentration = float(counts.iloc[0] / n)
    recovered = dominant is not None and concentration >= _RECOVERY_CONCENTRATION

    note = (
        f"cluster {dominant}, {concentration:.0%} of {n} matching articles"
        if recovered
        else (
            f"best cluster {dominant} holds {concentration:.0%} of {n} matching "
            f"articles (need {_RECOVERY_CONCENTRATION:.0%})"
            if dominant is not None
            else f"all {n} matching articles are outliers"
        )
    )
    return {
        "anchor_id": anchor["id"],
        "recovered": recovered,
        "n_articles": n,
        "dominant_cluster": dominant,
        "concentration": concentration,
        "note": note,
    }


def validate_anchor_recovery(
    df: pd.DataFrame,
    anchor_ids: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run anchor recovery check against a clustered articles DataFrame.

    Parameters
    ----------
    df         : clustered articles parquet loaded as DataFrame
    anchor_ids : subset of anchor IDs to check, or None for all 10
    cfg        : master config dict; loaded from disk if None

    Returns list of per-anchor result dicts with keys:
        anchor_id, recovered, n_articles, dominant_cluster, concentration, note
    """
    if cfg is None:
        cfg = load_config()

    tolerance = cfg["validation"]["anchor_tolerance_days"]
    anchors = _load_anchors(anchor_ids)

    results = []
    for anchor in anchors:
        anchor_df = _find_anchor_articles(df, anchor, tolerance)
        result = _check_recovery(anchor_df, anchor)
        results.append(result)
        status = "+" if result["recovered"] else "-"
        log.info("%s %s -- %s", status, anchor["id"], result["note"])

    n_recovered = sum(1 for r in results if r["recovered"])
    log.info(
        "Anchor recovery rate: %d/%d (reported, not gated -- ADR-019)",
        n_recovered,
        len(results),
    )
    return results
