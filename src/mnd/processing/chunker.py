"""Document chunker for the Phase 2 semantic corpus.

ADR-008 decision:
  Documents over 2,000 words are split into overlapping 600-token chunks
  with 100-token overlap before embedding. Each chunk carries full
  document-level metadata. For dynamics counting, count by document
  (not by chunk) to avoid inflating institutional source volume.

Tokenization:
  We use tiktoken (cl100k_base encoding) as a token-count proxy that is
  consistent across runs regardless of the embedding model. The 600-token
  chunk size maps to roughly 400–500 words of English prose — comfortably
  within Qwen3-Embedding-0.6B's effective window even at 512-token override.

Input:  pandas DataFrame with columns matching the Article schema
        (body, word_count, article_id, source_id, published_at, …)
Output: pandas DataFrame with same columns plus:
        chunk_id        article_id + '_c{n:03d}'
        chunk_index     0-based chunk sequence within the document
        chunk_total     total chunks for this document
        is_chunked      True if document was split (>2000 words)

Documents at or under 2,000 words are passed through unchanged with
chunk_index=0, chunk_total=1, is_chunked=False.

Usage:

    from mnd.processing.chunker import chunk_corpus
    chunked = chunk_corpus(articles_df)
    chunked.to_parquet("data/processed/chunks.parquet", index=False)
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from mnd.utils.logging import get_logger

log = get_logger(__name__)

# Thresholds from ADR-008 (config/config.yaml does not expose these since
# they are processing parameters, not modelling parameters).
_WORD_COUNT_THRESHOLD = 2_000
_CHUNK_TOKENS = 600
_OVERLAP_TOKENS = 100


def _get_tokenizer():
    """Return a tiktoken BPE tokenizer (cl100k_base). Cached after first call."""
    try:
        import tiktoken  # type: ignore[import-untyped]
        return tiktoken.get_encoding("cl100k_base")
    except ImportError as exc:
        raise ImportError(
            "tiktoken is required for document chunking: pip install tiktoken"
        ) from exc


def _split_into_chunks(text: str, enc, chunk_tokens: int, overlap_tokens: int) -> list[str]:
    """Tokenize text, split into overlapping windows, decode back to strings."""
    token_ids = enc.encode(text)
    if len(token_ids) <= chunk_tokens:
        return [text]
    step = chunk_tokens - overlap_tokens
    chunks: list[str] = []
    start = 0
    while start < len(token_ids):
        end = min(start + chunk_tokens, len(token_ids))
        chunk_ids = token_ids[start:end]
        chunk_text = enc.decode(chunk_ids)
        chunks.append(chunk_text)
        if end == len(token_ids):
            break
        start += step
    return chunks


def chunk_document(row: dict[str, Any], enc) -> list[dict[str, Any]]:
    """Chunk a single document row. Returns list of chunk dicts."""
    body: str = row.get("body", "") or ""
    word_count: int = row.get("word_count", len(body.split()))

    if word_count <= _WORD_COUNT_THRESHOLD:
        out = dict(row)
        out["chunk_id"] = row["article_id"] + "_c000"
        out["chunk_index"] = 0
        out["chunk_total"] = 1
        out["is_chunked"] = False
        return [out]

    chunks = _split_into_chunks(body, enc, _CHUNK_TOKENS, _OVERLAP_TOKENS)
    result: list[dict[str, Any]] = []
    for i, chunk_text in enumerate(chunks):
        out = dict(row)
        out["body"] = chunk_text
        out["word_count"] = len(chunk_text.split())
        out["chunk_id"] = f"{row['article_id']}_c{i:03d}"
        out["chunk_index"] = i
        out["chunk_total"] = len(chunks)
        out["is_chunked"] = True
        result.append(out)
    return result


def chunk_corpus(
    df: pd.DataFrame,
    *,
    chunk_tokens: int = _CHUNK_TOKENS,
    overlap_tokens: int = _OVERLAP_TOKENS,
    word_threshold: int = _WORD_COUNT_THRESHOLD,
) -> pd.DataFrame:
    """Chunk all documents in df that exceed word_threshold.

    Returns a new DataFrame with chunk records. Documents at or below
    the threshold pass through with chunk metadata columns added.

    Parameters
    ----------
    df : DataFrame
        Must contain at minimum: article_id, body, word_count.
    chunk_tokens : int
        Target chunk size in BPE tokens (default 600).
    overlap_tokens : int
        Overlap between consecutive chunks in tokens (default 100).
    word_threshold : int
        Documents with more than this many words are split (default 2000).
    """
    enc = _get_tokenizer()

    total_docs = len(df)
    chunked_docs = (df["word_count"] > word_threshold).sum()
    log.info(
        "Chunking corpus: %d documents, %d exceed %d-word threshold",
        total_docs, chunked_docs, word_threshold,
    )

    rows_out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        chunks = chunk_document(
            row.to_dict(),
            enc,
        )
        rows_out.extend(chunks)

    result = pd.DataFrame(rows_out)
    log.info(
        "Chunking complete: %d documents → %d chunks (%.1fx expansion)",
        total_docs, len(result), len(result) / max(total_docs, 1),
    )
    return result


def merge_chunk_embeddings(
    chunk_df: pd.DataFrame,
    embeddings,  # np.ndarray — left untyped to avoid an import-only annotation
):
    """For dynamics counting: return document-level (not chunk-level) records.

    When a document is chunked, keep only the first chunk's embedding as
    the document representative. This prevents institutional sources (which
    publish long documents) from inflating cluster volume counts.

    Returns
    -------
    doc_df : DataFrame
        One row per original article_id (deduped on article_id + chunk_index=0).
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
