"""Top-5 similar past narratives per cluster (ADR-019 section H).

Three complementary similarity measures reported separately:

  semantic       cosine on cluster embedding centroids (Reimers & Gurevych 2019)
  lexical        Jaccard overlap on top-K c-TF-IDF terms (Jaccard 1901; K=10)
  morphological  Pearson correlation on normalized weekly volume curves

Top-K ranking (K=5) rather than a similarity threshold -- follows the BEIR
recall@5 convention (Thakur et al. 2021) and avoids the unanchored
"where's the cutoff" question.

Symmetric measures: for any pair (a, b), sim(a, b) == sim(b, a). Self-pairs
are excluded from each cluster's top-5.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

DEFAULT_TOP_K = 5
DEFAULT_LEXICAL_TOP_TERMS = 10


def _topk_indices(scores: np.ndarray, k: int, self_idx: int) -> list[int]:
    """Indices of the top-k scores, excluding self_idx, in descending order."""
    masked = scores.copy()
    masked[self_idx] = -np.inf
    if k >= len(masked):
        order = np.argsort(masked)[::-1]
    else:
        # argpartition for k largest, then sort that slice
        part = np.argpartition(masked, -k)[-k:]
        order = part[np.argsort(masked[part])[::-1]]
    return [int(i) for i in order if masked[i] > -np.inf][:k]


def semantic_similarity(
    cluster_ids: list[int | str],
    centroids: np.ndarray,
    top_k: int = DEFAULT_TOP_K,
) -> dict[int | str, list[int | str]]:
    """Top-k clusters by cosine similarity on embedding centroids.

    Parameters
    ----------
    cluster_ids : list of cluster identifiers, length C
    centroids   : (C, D) float array of cluster mean embeddings
    """
    if len(cluster_ids) != centroids.shape[0]:
        raise ValueError("cluster_ids length must equal centroids.shape[0]")
    norms = np.linalg.norm(centroids, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normed = centroids / norms
    sims = normed @ normed.T

    out: dict[int | str, list[int | str]] = {}
    for i, cid in enumerate(cluster_ids):
        idxs = _topk_indices(sims[i], top_k, self_idx=i)
        out[cid] = [cluster_ids[j] for j in idxs]
    return out


def lexical_similarity(
    cluster_ids: list[int | str],
    top_terms: dict[int | str, Iterable[str]],
    top_k: int = DEFAULT_TOP_K,
) -> dict[int | str, list[int | str]]:
    """Top-k clusters by Jaccard overlap on top-K c-TF-IDF terms.

    Parameters
    ----------
    cluster_ids : list of cluster identifiers
    top_terms   : mapping cluster_id -> iterable of representative terms
                  (typically the top-10 c-TF-IDF terms from BERTopic)
    """
    term_sets: dict[int | str, set[str]] = {
        cid: set(top_terms.get(cid, ())) for cid in cluster_ids
    }

    C = len(cluster_ids)
    sims = np.zeros((C, C), dtype=float)
    for i, ci in enumerate(cluster_ids):
        a = term_sets[ci]
        for j in range(i + 1, C):
            b = term_sets[cluster_ids[j]]
            union = a | b
            if not union:
                jacc = 0.0
            else:
                jacc = len(a & b) / len(union)
            sims[i, j] = jacc
            sims[j, i] = jacc

    out: dict[int | str, list[int | str]] = {}
    for i, cid in enumerate(cluster_ids):
        idxs = _topk_indices(sims[i], top_k, self_idx=i)
        out[cid] = [cluster_ids[j] for j in idxs]
    return out


def morphological_similarity(
    cluster_ids: list[int | str],
    volume_curves: dict[int | str, pd.Series],
    top_k: int = DEFAULT_TOP_K,
) -> dict[int | str, list[int | str]]:
    """Top-k clusters by Pearson correlation on shape-aligned volume curves.

    Each curve is realigned to its onset (sorted by index, dropping leading
    zeros) so the comparison is over relative time-since-emergence rather
    than absolute calendar time -- two bumps separated by years still
    resemble each other if their shapes match. Curves are then padded to a
    common length with zeros, mean-centered, and unit-normalized for
    Pearson correlation.

    Parameters
    ----------
    cluster_ids   : list of cluster identifiers
    volume_curves : mapping cluster_id -> pd.Series indexed by week_start
                    (smoothed_combined from smooth_combined())
    """
    if not cluster_ids:
        return {}

    shape_vectors: list[np.ndarray] = []
    for cid in cluster_ids:
        s = volume_curves.get(cid)
        if s is None or s.empty:
            shape_vectors.append(np.zeros(0, dtype=float))
            continue
        ordered = s.sort_index().to_numpy(dtype=float)
        ordered = np.nan_to_num(ordered, nan=0.0)
        # Strip leading zeros so the curve is anchored to its onset
        nonzero = np.flatnonzero(ordered)
        if nonzero.size:
            ordered = ordered[nonzero[0] :]
        shape_vectors.append(ordered)

    max_len = max((v.size for v in shape_vectors), default=0)
    aligned = np.zeros((len(cluster_ids), max(max_len, 1)), dtype=float)
    for i, v in enumerate(shape_vectors):
        aligned[i, : v.size] = v

    means = aligned.mean(axis=1, keepdims=True)
    centered = aligned - means
    norms = np.linalg.norm(centered, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normed = centered / norms
    sims = normed @ normed.T

    out: dict[int | str, list[int | str]] = {}
    for i, cid in enumerate(cluster_ids):
        idxs = _topk_indices(sims[i], top_k, self_idx=i)
        out[cid] = [cluster_ids[j] for j in idxs]
    return out


def compute_similar_narratives(
    cluster_ids: list[int | str],
    *,
    centroids: np.ndarray,
    top_terms: dict[int | str, Iterable[str]],
    volume_curves: dict[int | str, pd.Series],
    top_k: int = DEFAULT_TOP_K,
) -> dict[int | str, dict[str, list[int | str]]]:
    """Compute all three top-k similarity measures per cluster (ADR-019 section H).

    Returns: cluster_id -> {"semantic": [...], "lexical": [...], "morphological": [...]}
    Each inner list has up to top_k cluster_ids, descending similarity, self excluded.
    """
    sem = semantic_similarity(cluster_ids, centroids, top_k)
    lex = lexical_similarity(cluster_ids, top_terms, top_k)
    morph = morphological_similarity(cluster_ids, volume_curves, top_k)
    return {
        cid: {
            "semantic": sem[cid],
            "lexical": lex[cid],
            "morphological": morph[cid],
        }
        for cid in cluster_ids
    }
