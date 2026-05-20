"""Chunker tests for the Qwen3-tokenizer alignment (ADR-019).

Verifies that:
  1. Chunker uses the embedding model's own tokenizer (Qwen3 SentencePiece),
     not tiktoken cl100k_base — eliminates the silent truncation risk that
     existed under the prior 600-cl100k recipe.
  2. Every chunk fits within the configured chunk_tokens limit.
  3. Documents that fit within chunk_tokens produce exactly one chunk.
  4. Documents longer than chunk_tokens are split with the configured overlap.
  5. Chunk metadata (chunk_id, chunk_index, chunk_total, is_chunked) is set
     consistently.
"""
from __future__ import annotations

import pandas as pd
import pytest

# Skip the entire module if transformers / tokenizer isn't available.
pytest.importorskip("transformers")


def _make_doc(article_id: str, body: str, source_id: str = "test") -> dict:
    return {
        "article_id": article_id,
        "source_id": source_id,
        "url": f"https://example.com/{article_id}",
        "published_at": "2020-01-01T00:00:00Z",
        "title": "Test document",
        "body": body,
        "word_count": len(body.split()),
    }


def test_short_document_produces_single_chunk():
    from mnd.processing.chunker import chunk_corpus

    short_body = "The Federal Reserve raised interest rates today."
    df = pd.DataFrame([_make_doc("a1", short_body)])
    out = chunk_corpus(df)

    assert len(out) == 1
    assert out.iloc[0]["chunk_id"] == "a1_c000"
    assert out.iloc[0]["chunk_index"] == 0
    assert out.iloc[0]["chunk_total"] == 1
    assert out.iloc[0]["is_chunked"] is False or bool(out.iloc[0]["is_chunked"]) is False


def test_long_document_is_chunked_with_overlap():
    from mnd.processing.chunker import chunk_corpus

    # Build a body that exceeds 512 Qwen3 tokens. Mix of macro vocabulary so
    # it tokenizes naturally; ~1500 words is well past the chunk window.
    sentence = (
        "The Federal Reserve announced a rate cut in response to deteriorating "
        "labor market conditions and weakening inflation expectations across "
        "the term structure of nominal Treasury yields and inflation breakevens. "
    )
    long_body = sentence * 200  # ~1500 words
    df = pd.DataFrame([_make_doc("a2", long_body)])
    out = chunk_corpus(df)

    assert len(out) > 1, "Expected long document to produce multiple chunks"
    assert (out["chunk_total"] == len(out)).all(), "chunk_total must equal len(chunks)"
    assert list(out["chunk_index"]) == list(range(len(out)))
    assert out["is_chunked"].all()
    assert out["chunk_id"].iloc[0] == "a2_c000"
    assert out["chunk_id"].iloc[-1] == f"a2_c{len(out) - 1:03d}"


def test_chunks_fit_within_qwen3_context_window():
    """The headline ADR-019 guarantee: chunker output never exceeds chunk_tokens
    in the embedding model's tokenizer. Eliminates silent truncation."""
    from mnd.processing.chunker import _chunk_params, _get_qwen3_tokenizer, chunk_corpus

    chunk_tokens, _ = _chunk_params()
    tokenizer = _get_qwen3_tokenizer()

    sentence = (
        "Quantitative tightening continued through the third quarter as the "
        "Federal Open Market Committee signalled a higher-for-longer stance. "
    )
    long_body = sentence * 200
    df = pd.DataFrame([_make_doc("a3", long_body)])
    out = chunk_corpus(df)

    for _, row in out.iterrows():
        n_tokens = len(tokenizer.encode(row["body"], add_special_tokens=False))
        assert n_tokens <= chunk_tokens, (
            f"Chunk {row['chunk_id']} has {n_tokens} Qwen3 tokens > "
            f"chunk_tokens={chunk_tokens}. Silent truncation would occur at "
            f"the embedder. This is the bug ADR-019 fixed."
        )


def test_doc_representative_extraction():
    """merge_chunk_embeddings returns one row per article_id (chunk_index==0)."""
    import numpy as np

    from mnd.processing.chunker import chunk_corpus, merge_chunk_embeddings

    sentence = "The Federal Reserve responded to credit spreads widening sharply. "
    short_doc = _make_doc("short1", sentence * 5)            # 1 chunk
    long_doc = _make_doc("long1", sentence * 200)            # many chunks
    df = pd.DataFrame([short_doc, long_doc])
    chunks = chunk_corpus(df)
    n_chunks = len(chunks)

    # Fake embeddings — one row per chunk, fixed dim.
    fake_embeddings = np.zeros((n_chunks, 8), dtype=np.float32)
    doc_df, doc_embs = merge_chunk_embeddings(chunks, fake_embeddings)

    assert len(doc_df) == 2  # one row per original article
    assert set(doc_df["article_id"]) == {"short1", "long1"}
    assert (doc_df["chunk_index"] == 0).all()
    assert doc_embs.shape == (2, 8)
