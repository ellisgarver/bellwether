"""Incremental weekly merge via merge_models (ADR-066).

The anchor-id-stability test is the credibility gate: a weekly merge must preserve
every existing topic id (a tracked narrative must not be renumbered). Marked
integration because it fits BERTopic; run with `-m integration`.
"""
from __future__ import annotations

import numpy as np
import pytest

from mnd.utils.config import load_config


def _angular_topics(seed: int = 7, dim: int = 64):
    """Well-separated topic directions on the unit sphere (realistic embedding shape)."""
    rng = np.random.default_rng(seed)
    norm = lambda a: a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-9)
    dirs = [norm(rng.normal(0, 1, dim)) for _ in range(4)]
    mk = lambda k, n: norm(dirs[k] + rng.normal(0, 0.12, (n, dim))).astype("float32")
    return mk


@pytest.mark.integration
def test_weekly_merge_preserves_anchor_ids_and_appends_new():
    from mnd.clustering.bertopic_pipeline import _build_model
    from mnd.clustering.incremental import (
        _nonnoise_ids,
        anchors_keep_ids,
        merge_new_week,
    )

    cfg = load_config()
    cfg["clustering"]["umap"]["n_neighbors"] = 8
    cfg["clustering"]["hdbscan"]["min_cluster_size"] = 5
    mk = _angular_topics()
    words = ["alpha", "beta", "gamma", "delta"]

    # Base corpus: three narratives (topics 0,1,2).
    base_emb = np.vstack([mk(0, 40), mk(1, 40), mk(2, 40)])
    base_docs = [f"{words[k]} doc {i}" for k in range(3) for i in range(40)]
    base = _build_model(cfg, 42)
    base.fit_transform(base_docs, base_emb)
    base_ids = _nonnoise_ids(base)
    assert len(base_ids) >= 2  # sanity: the base actually clustered

    # New week: extend all three + one genuinely-new narrative (topic 3).
    new_emb = np.vstack([mk(0, 15), mk(1, 15), mk(2, 15), mk(3, 20)])
    new_docs = (
        [f"{words[k]} doc n{i}" for k, n in [(0, 15), (1, 15), (2, 15)] for i in range(n)]
        + [f"delta doc n{i}" for i in range(20)]
    )

    merged, new_topics = merge_new_week(base, new_docs, new_emb, cfg, min_similarity=0.9)

    # (1) Anchor-id stability: every base topic id survives the merge.
    ok, missing = anchors_keep_ids(base, merged, base_ids)
    assert ok, f"anchor ids renumbered by the merge: {missing}"

    # (2) A genuinely-new narrative appears as a new id beyond the base set.
    merged_ids = _nonnoise_ids(merged)
    appended = set(merged_ids) - set(base_ids)
    assert appended, "the new narrative was not appended as a new topic id"

    # (3) The new week's delta docs route to the appended id, not an existing one.
    delta_assignments = set(new_topics[-20:])
    assert delta_assignments & appended, "new-narrative docs were absorbed into an existing id"


# ---------------------------------------------------------------------------
# ADR-066 Part C: post-merge clusters-frame assembly
# ---------------------------------------------------------------------------

import pandas as pd
import pytest

from mnd.clustering.incremental import assemble_merged_clusters


def _chunks(ids):
    return pd.DataFrame({"chunk_id": ids, "title": ["t"] * len(ids), "body": ["b"] * len(ids)})


def test_assemble_preserves_order_and_old_assignments():
    chunks = _chunks(["a_c000", "a_c001", "b_c000", "NEW_c000"])
    old = pd.DataFrame({"chunk_id": ["a_c000", "a_c001", "b_c000"], "topic": [3, 3, -1]})
    out = assemble_merged_clusters(chunks, old, {"NEW_c000": 7})
    assert list(out["chunk_id"]) == list(chunks["chunk_id"])  # embedding alignment
    assert list(out["topic"]) == [3, 3, -1, 7]                # old kept, delta assigned


def test_assemble_refuses_unassigned_chunks():
    chunks = _chunks(["a_c000", "orphan_c000"])
    old = pd.DataFrame({"chunk_id": ["a_c000"], "topic": [1]})
    with pytest.raises(RuntimeError, match="no topic assignment"):
        assemble_merged_clusters(chunks, old, {})
