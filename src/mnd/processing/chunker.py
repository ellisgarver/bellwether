"""Document chunker.

Splits documents into overlapping chunks that fit within the embedding model's
context window. Anchored to the BEIR retrieval-evaluation convention (Thakur
et al. 2021, NeurIPS): 512 word pieces per chunk, with overlap in the field-
standard 10-20% band (LangChain/LlamaIndex library defaults).

Uses the embedding model's own tokenizer (Qwen3 SentencePiece) so chunk size in
tokens maps 1:1 to the model's effective sequence length. Documents that fit
within the chunk window produce a single chunk; there is no word-count gate.

Input:  pandas DataFrame matching the Article schema (article_id, body, title,
        word_count, source_id, published_at, ...).
Output: pandas DataFrame with same columns plus:
        chunk_id        article_id + '_c{n:03d}'
        chunk_index     0-based chunk sequence within the document
        chunk_total     total chunks for this document
        is_chunked      True if the document was split into more than one chunk

Volume counting uses document representatives (chunk_index == 0), not chunks.
See ``merge_chunk_embeddings``.
"""
from __future__ import annotations

import functools
from typing import Any

import pandas as pd

from mnd.utils.config import load_config
from mnd.utils.logging import get_logger

log = get_logger(__name__)


@functools.lru_cache(maxsize=1)
def _get_qwen3_tokenizer():
    """Return the configured Qwen3-Embedding tokenizer (8B; ADR-036). Cached.

    Loaded from config.embedding.primary.model so it always matches the
    embedder. The Qwen3-Embedding family shares one tokenizer across sizes,
    so 512-token chunk boundaries are identical whichever size is configured.
    """
    cfg = load_config()
    model_name = cfg["embedding"]["primary"]["model"]
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise ImportError(
            "transformers is required for chunking. "
            "Install with `pip install transformers`."
        ) from exc
    return AutoTokenizer.from_pretrained(model_name)


def _chunk_params() -> tuple[int, int]:
    """Read chunk size and overlap from config.processing.chunking."""
    cfg = load_config()
    chunk_cfg = cfg.get("processing", {}).get("chunking", {})
    chunk_tokens = int(chunk_cfg.get("chunk_tokens", 512))
    chunk_overlap = int(chunk_cfg.get("chunk_overlap", 64))
    if chunk_overlap >= chunk_tokens:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be < chunk_tokens ({chunk_tokens})"
        )
    return chunk_tokens, chunk_overlap


def _split_into_chunks(
    text: str,
    tokenizer,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Tokenize text with the embedder's tokenizer, split into overlapping
    windows, decode back to strings.

    Documents at or below ``chunk_tokens`` produce exactly one chunk.
    """
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= chunk_tokens:
        return [text]
    step = chunk_tokens - overlap_tokens
    chunks: list[str] = []
    start = 0
    while start < len(token_ids):
        end = min(start + chunk_tokens, len(token_ids))
        chunk_ids = token_ids[start:end]
        chunk_text = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        chunks.append(chunk_text)
        if end == len(token_ids):
            break
        start += step
    return chunks


def chunk_document(row: dict[str, Any], tokenizer, chunk_tokens: int, overlap_tokens: int) -> list[dict[str, Any]]:
    """Chunk a single document row. Returns a list of chunk dicts."""
    body: str = row.get("body", "") or ""

    chunks = _split_into_chunks(body, tokenizer, chunk_tokens, overlap_tokens)
    result: list[dict[str, Any]] = []
    for i, chunk_text in enumerate(chunks):
        out = dict(row)
        out["body"] = chunk_text
        out["word_count"] = len(chunk_text.split())
        out["chunk_id"] = f"{row['article_id']}_c{i:03d}"
        out["chunk_index"] = i
        out["chunk_total"] = len(chunks)
        out["is_chunked"] = len(chunks) > 1
        result.append(out)
    return result


def chunk_corpus(
    df: pd.DataFrame,
    *,
    chunk_tokens: int | None = None,
    chunk_overlap: int | None = None,
) -> pd.DataFrame:
    """Chunk all documents in df. Documents that fit within ``chunk_tokens``
    pass through as a single chunk. Documents that exceed are split into
    overlapping ``chunk_tokens``-sized windows with ``chunk_overlap`` token
    overlap.

    Parameters
    ----------
    df : DataFrame
        Must contain at minimum: article_id, body. Other Article fields are
        preserved on each chunk row.
    chunk_tokens : int, optional
        Override config.processing.chunking.chunk_tokens (default 512 per
        BEIR convention).
    chunk_overlap : int, optional
        Override config.processing.chunking.chunk_overlap (default 64).
    """
    cfg_chunk_tokens, cfg_overlap = _chunk_params()
    chunk_tokens = chunk_tokens if chunk_tokens is not None else cfg_chunk_tokens
    chunk_overlap = chunk_overlap if chunk_overlap is not None else cfg_overlap

    tokenizer = _get_qwen3_tokenizer()

    total_docs = len(df)
    log.info(
        "Chunking corpus: %d documents (chunk_tokens=%d, overlap=%d, tokenizer=%s)",
        total_docs, chunk_tokens, chunk_overlap, tokenizer.__class__.__name__,
    )

    rows_out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        chunks = chunk_document(row.to_dict(), tokenizer, chunk_tokens, chunk_overlap)
        rows_out.extend(chunks)

    result = pd.DataFrame(rows_out)
    n_chunked = int((result["is_chunked"]).sum() // max(result["chunk_total"].max(), 1)) if len(result) else 0
    log.info(
        "Chunking complete: %d documents -> %d chunks (%.2fx expansion)",
        total_docs, len(result), len(result) / max(total_docs, 1),
    )
    return result


def merge_chunk_embeddings(
    chunk_df: pd.DataFrame,
    embeddings,  # np.ndarray — left untyped to avoid a numpy-only annotation
):
    """For dynamics counting: return document-level (not chunk-level) records.

    When a document is chunked, keep only the first chunk's embedding as the
    document representative. Prevents long institutional documents from
    inflating cluster volume counts.

    Returns
    -------
    doc_df : DataFrame
        One row per original article_id (deduped on chunk_index == 0).
    doc_embeddings : np.ndarray
        Embeddings aligned to doc_df.
    """
    mask = (chunk_df["chunk_index"] == 0).values
    doc_df = chunk_df[mask].copy()
    doc_embeddings = embeddings[mask]
    log.info(
        "Reduced %d chunks to %d document representatives for dynamics counting",
        len(chunk_df), len(doc_df),
    )
    return doc_df, doc_embeddings
