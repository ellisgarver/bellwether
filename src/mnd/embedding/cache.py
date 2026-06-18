"""Incremental embedding cache (ADR-050).

Lets the ``embed`` step reuse previously-computed vectors for chunks whose
``(chunk_id, embedded-text)`` pair is unchanged, so a weekly re-ingest re-embeds
only genuinely new or changed chunks instead of the whole corpus.

On-disk contract — a matched pair, both row-aligned to ``chunks.parquet``:

  - ``embeddings.npy``         ``(N, D)`` float32 — the vectors (unchanged contract)
  - ``embeddings_index.parquet`` columns ``[chunk_id, text_sha1]``

``cluster`` / ``analyze`` keep reading ``embeddings.npy`` positionally; the index
is a sidecar they never open. A full rebuild (archive / NUKE wipes
``data/processed``) leaves no cache, so ``embed`` re-encodes everything; a delta
run (``SKIP_CLEANUP=1``) keeps the pair, so ``embed`` reuses it.

The cache key is ``(chunk_id, text_sha1)`` — not ``chunk_id`` alone — because
``chunk_id`` is derived from ``source_id|url`` and is stable across re-captures.
A corrected / more-complete re-capture of an existing URL keeps its ``chunk_id``
but changes its body, so keying on the text hash forces a re-embed instead of
serving a stale vector.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


def index_path_for(npy_path: Path) -> Path:
    """The sidecar index path for an embeddings ``.npy`` (single definition)."""
    return npy_path.with_name(f"{npy_path.stem}_index.parquet")


def build_chunk_text(row: dict) -> str:
    """The exact string fed to the embedder for one chunk row.

    Single source of truth so ``embed`` and the index backfill hash identical
    text. Mirrors the title/body concatenation the embedder consumes; the
    constant instruction prefix is applied inside ``Embedder.encode`` and is not
    part of the content identity.
    """
    title = str(row.get("title") or "").strip()
    body = str(row.get("body") or "").strip()
    if title and body:
        return f"{title}. {body}"
    return title or body


def text_sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


@dataclass
class IncrementalPlan:
    """Per-row decision for one embed run, aligned to ``chunk_df`` order."""

    texts: list[str]              # embedded text per row
    chunk_ids: list[str]          # chunk_id per row
    text_hashes: list[str]        # text_sha1 per row
    encode_positions: list[int]   # row indices that must be encoded fresh
    reuse_src: dict[int, int]     # new_row_idx -> row_idx in the cached matrix

    @property
    def n_reuse(self) -> int:
        return len(self.reuse_src)

    @property
    def n_encode(self) -> int:
        return len(self.encode_positions)


def plan_incremental(
    chunk_df: pd.DataFrame,
    cached_index: pd.DataFrame | None,
) -> IncrementalPlan:
    """Decide which rows to encode fresh vs. reuse from the cache.

    A row is reusable iff its ``(chunk_id, text_sha1)`` is present in
    ``cached_index``. Pass ``cached_index=None`` (or an empty frame) to force a
    full encode — the returned plan still carries the per-row ids/hashes needed
    to write a fresh index.
    """
    records = chunk_df.to_dict("records")
    texts = [build_chunk_text(r) for r in records]
    chunk_ids = [str(r["chunk_id"]) for r in records]
    text_hashes = [text_sha1(t) for t in texts]

    cache_pos: dict[tuple[str, str], int] = {}
    if cached_index is not None and len(cached_index):
        for i, (cid, h) in enumerate(
            zip(
                cached_index["chunk_id"].astype(str),
                cached_index["text_sha1"].astype(str),
            )
        ):
            cache_pos.setdefault((cid, h), i)

    encode_positions: list[int] = []
    reuse_src: dict[int, int] = {}
    for new_i, key in enumerate(zip(chunk_ids, text_hashes)):
        src = cache_pos.get(key)
        if src is None:
            encode_positions.append(new_i)
        else:
            reuse_src[new_i] = src

    return IncrementalPlan(
        texts=texts,
        chunk_ids=chunk_ids,
        text_hashes=text_hashes,
        encode_positions=encode_positions,
        reuse_src=reuse_src,
    )


def assemble_matrix(
    plan: IncrementalPlan,
    cached_matrix: np.ndarray | None,
    fresh: np.ndarray,
) -> np.ndarray:
    """Stitch reused + freshly-encoded rows into one ``(N, D)`` matrix in
    ``chunk_df`` order.

    ``fresh`` holds the encoded vectors for ``plan.encode_positions`` in that
    order; reused rows are copied from ``cached_matrix``.
    """
    if fresh.size:
        dim = fresh.shape[1]
    elif cached_matrix is not None and cached_matrix.size:
        dim = cached_matrix.shape[1]
    else:
        raise ValueError("no rows to assemble (empty fresh batch and empty cache)")

    out = np.empty((len(plan.chunk_ids), dim), dtype=np.float32)
    for fresh_i, new_i in enumerate(plan.encode_positions):
        out[new_i] = fresh[fresh_i]
    if plan.reuse_src:
        if cached_matrix is None:
            raise ValueError("plan reuses cached rows but no cached_matrix was given")
        for new_i, src in plan.reuse_src.items():
            out[new_i] = cached_matrix[src]
    return out


def index_frame(plan: IncrementalPlan) -> pd.DataFrame:
    """The sidecar frame to persist next to ``embeddings.npy``."""
    return pd.DataFrame({"chunk_id": plan.chunk_ids, "text_sha1": plan.text_hashes})
