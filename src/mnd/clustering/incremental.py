"""Incremental weekly re-cluster via BERTopic ``merge_models`` (ADR-066).

The weekly refresh must fold a new week of articles into the existing narrative set
so that **every existing topic keeps its id** — and therefore its narrative-page URL
and its ADR-056 human name — while genuinely-new stories appear as new topics. That
identity invariant is the whole point of tracking narratives over time (ADR-057 §3).

BERTopic's ``merge_models`` gives exactly this: the first (base) model is the
baseline, its topic ids are preserved, and each topic in the new-week model is
either re-assigned to a base topic (when their topic embeddings are within
``min_similarity``) or appended as a new topic id. New-week documents are then
assigned with ``merged.transform`` — validated to route continuing-story docs to the
kept base id and genuinely-new docs to the appended id.

This module is the mechanism only; wiring it into ``update`` is gated on the
anchor-id-stability check (ADR-066): a synthetic weekly merge must not renumber any
of the ten anchor narratives. Until that passes on the real corpus, ``update`` parks
new institutional articles and the narrative set stays "as of the last full build".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from mnd.utils.logging import get_logger

log = get_logger(__name__)


def load_base_model(model_dir: str | Path) -> Any:
    """Load the persisted base BERTopic model (ADR-066 Part A)."""
    from bertopic import BERTopic

    return BERTopic.load(str(model_dir))


def merge_new_week(
    base_model: Any,
    new_docs: list[str],
    new_embeddings: np.ndarray,
    cfg: dict[str, Any],
    min_similarity: float,
) -> tuple[Any, list[int]]:
    """Merge a new week into the base model, preserving existing topic ids (ADR-066).

    Fits a BERTopic model on the new-week docs (with their precomputed embeddings),
    then ``merge_models([base, new], min_similarity)``. Returns the merged model and
    the new-week documents' topic ids under the merged id space (existing ids for
    continuing stories, appended ids for genuinely-new ones). Existing documents keep
    their base ids unchanged — those are preserved by ``merge_models`` by
    construction and are not recomputed here.
    """
    from bertopic import BERTopic

    from mnd.clustering.bertopic_pipeline import _build_model

    seed = int(cfg["reproducibility"]["global_random_seed"])
    new_model = _build_model(cfg, seed)
    new_model.fit_transform(new_docs, new_embeddings)

    merged = BERTopic.merge_models(
        [base_model, new_model], min_similarity=float(min_similarity)
    )
    new_topics, _ = merged.transform(new_docs, new_embeddings)
    new_topics = [int(t) for t in new_topics]

    base_ids = _nonnoise_ids(base_model)
    merged_ids = _nonnoise_ids(merged)
    appended = sorted(set(merged_ids) - set(base_ids))
    log.info(
        "merge_new_week (ADR-066): base %d topics → merged %d (%d appended); "
        "new-week docs assigned to %d existing + %d new topics (min_similarity=%.2f)",
        len(base_ids), len(merged_ids), len(appended),
        len(set(new_topics) & set(base_ids)), len(set(new_topics) & set(appended)),
        min_similarity,
    )
    return merged, new_topics


def anchors_keep_ids(
    base_model: Any,
    merged_model: Any,
    anchor_topic_ids: list[int],
) -> tuple[bool, list[int]]:
    """Check that every anchor's base topic id survives the merge unchanged (ADR-066).

    The credibility gate for the weekly path: ``merge_models`` must not renumber a
    tracked narrative. Returns ``(ok, missing)`` where ``missing`` are anchor ids that
    are no longer present as topics in the merged model.
    """
    merged_ids = set(_nonnoise_ids(merged_model))
    missing = [tid for tid in anchor_topic_ids if tid not in merged_ids]
    return (len(missing) == 0, missing)


def _nonnoise_ids(model: Any) -> list[int]:
    """Sorted non-noise topic ids of a fitted/merged BERTopic model."""
    info = model.get_topic_info()
    return sorted(int(t) for t in info["Topic"].tolist() if int(t) >= 0)
