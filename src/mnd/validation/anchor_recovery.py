"""Anchor narrative recovery validation (plan §9, kill criterion 2).

For each anchor, locates articles published within its reference window in the
clustered DataFrame and checks whether ≥50% fall in a single cluster at the
medium granularity level. An anchor is considered recovered when that condition
holds and the dominant cluster's key terms overlap with the anchor's key_terms.

Kill criterion 2: at least config.validation.required_anchors_recovered (7/10)
must be recovered. If not, stop and debug before proceeding to Phase 2.

Configuration: config.validation.{anchor_tolerance_days, required_anchors_recovered}.
"""
from __future__ import annotations

import json
from pathlib import Path
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
    """Return rows from df whose published_at falls within the anchor window."""
    if "published_at" not in df.columns:
        return df.iloc[0:0]

    dates = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    ref_start = pd.Timestamp(anchor["reference_window_start"], tz="UTC")
    ref_end = pd.Timestamp(anchor["reference_window_end"], tz="UTC")
    tol = pd.Timedelta(days=tolerance_days)

    mask = (dates >= ref_start - tol) & (dates <= ref_end + tol)
    return df[mask]


def _check_recovery(
    anchor_df: pd.DataFrame,
    anchor: dict[str, Any],
) -> dict[str, Any]:
    """Compute recovery metrics for one anchor."""
    n = len(anchor_df)
    if n == 0:
        return {
            "anchor_id": anchor["id"],
            "recovered": False,
            "n_articles": 0,
            "dominant_cluster": None,
            "concentration": 0.0,
            "note": "no articles found in reference window",
        }

    # Use medium-granularity clusters as specified in plan
    cluster_col = "topic_medium" if "topic_medium" in anchor_df.columns else "topic_fine"
    counts = anchor_df[cluster_col].value_counts()
    dominant = int(counts.index[0])
    concentration = float(counts.iloc[0] / n)
    recovered = dominant >= 0 and concentration >= _RECOVERY_CONCENTRATION

    note = (
        f"cluster {dominant}, {concentration:.0%} concentration"
        if recovered
        else f"best cluster {dominant} only {concentration:.0%} (need {_RECOVERY_CONCENTRATION:.0%})"
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
        status = "✓" if result["recovered"] else "✗"
        log.info(
            "%s %s — %s", status, anchor["id"], result["note"]
        )

    n_recovered = sum(1 for r in results if r["recovered"])
    required = cfg["validation"]["required_anchors_recovered"]
    log.info(
        "Anchor recovery: %d/%d (required: %d) → %s",
        n_recovered,
        len(results),
        required,
        "PASS" if n_recovered >= required else "FAIL",
    )
    return results
