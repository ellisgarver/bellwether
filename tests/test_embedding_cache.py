"""Unit tests for the incremental embedding cache (ADR-050, no ML deps)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mnd.embedding.cache import (
    assemble_matrix,
    build_chunk_text,
    index_frame,
    index_path_for,
    plan_incremental,
    text_sha1,
)


def _chunks(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """rows = [(chunk_id, title, body), ...]."""
    return pd.DataFrame(
        [{"chunk_id": c, "title": t, "body": b} for c, t, b in rows]
    )


class TestText:
    def test_title_and_body_joined(self):
        assert build_chunk_text({"title": "Fed", "body": "raised rates"}) == "Fed. raised rates"

    def test_title_only(self):
        assert build_chunk_text({"title": "Fed", "body": ""}) == "Fed"

    def test_body_only(self):
        assert build_chunk_text({"title": "", "body": "raised rates"}) == "raised rates"

    def test_missing_keys(self):
        assert build_chunk_text({}) == ""

    def test_sha1_stable_and_sensitive(self):
        assert text_sha1("abc") == text_sha1("abc")
        assert text_sha1("abc") != text_sha1("abd")


class TestIndexPath:
    def test_sibling_parquet(self):
        assert index_path_for(Path("/d/embeddings.npy")) == Path("/d/embeddings_index.parquet")


class TestPlanNoCache:
    def test_all_encoded_when_no_cache(self):
        df = _chunks([("a_c000", "t1", "b1"), ("b_c000", "t2", "b2")])
        plan = plan_incremental(df, cached_index=None)
        assert plan.encode_positions == [0, 1]
        assert plan.reuse_src == {}
        assert plan.chunk_ids == ["a_c000", "b_c000"]

    def test_empty_cache_frame_treated_as_no_cache(self):
        df = _chunks([("a_c000", "t1", "b1")])
        empty = pd.DataFrame({"chunk_id": [], "text_sha1": []})
        plan = plan_incremental(df, cached_index=empty)
        assert plan.encode_positions == [0]


class TestPlanIncremental:
    def _cached(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build a cache index that exactly matches df (everything reusable)."""
        return index_frame(plan_incremental(df, cached_index=None))

    def test_full_match_reuses_all(self):
        df = _chunks([("a_c000", "t1", "b1"), ("b_c000", "t2", "b2")])
        cached = self._cached(df)
        plan = plan_incremental(df, cached_index=cached)
        assert plan.n_encode == 0
        assert plan.n_reuse == 2
        assert plan.reuse_src == {0: 0, 1: 1}

    def test_changed_body_same_chunk_id_forces_reencode(self):
        old = _chunks([("a_c000", "t1", "b1")])
        cached = self._cached(old)
        # Same chunk_id (stable across re-capture) but corrected body → must re-embed.
        new = _chunks([("a_c000", "t1", "b1-corrected")])
        plan = plan_incremental(new, cached_index=cached)
        assert plan.encode_positions == [0]
        assert plan.reuse_src == {}

    def test_new_chunk_id_encoded_existing_reused(self):
        old = _chunks([("a_c000", "t1", "b1")])
        cached = self._cached(old)
        new = _chunks([("a_c000", "t1", "b1"), ("z_c000", "t9", "b9")])
        plan = plan_incremental(new, cached_index=cached)
        assert plan.reuse_src == {0: 0}
        assert plan.encode_positions == [1]

    def test_reorder_maps_to_correct_cache_rows(self):
        old = _chunks([("a_c000", "t1", "b1"), ("b_c000", "t2", "b2")])
        cached = self._cached(old)
        # New order swaps the two rows; cache lookup must follow content, not position.
        new = _chunks([("b_c000", "t2", "b2"), ("a_c000", "t1", "b1")])
        plan = plan_incremental(new, cached_index=cached)
        assert plan.reuse_src == {0: 1, 1: 0}
        assert plan.n_encode == 0

    def test_dropped_chunk_simply_absent(self):
        old = _chunks([("a_c000", "t1", "b1"), ("b_c000", "t2", "b2")])
        cached = self._cached(old)
        new = _chunks([("a_c000", "t1", "b1")])  # b dropped
        plan = plan_incremental(new, cached_index=cached)
        assert plan.chunk_ids == ["a_c000"]
        assert plan.reuse_src == {0: 0}


class TestAssemble:
    def test_full_encode_no_cache(self):
        df = _chunks([("a_c000", "t1", "b1"), ("b_c000", "t2", "b2")])
        plan = plan_incremental(df, cached_index=None)
        fresh = np.array([[1.0, 1.0], [2.0, 2.0]], dtype=np.float32)
        out = assemble_matrix(plan, cached_matrix=None, fresh=fresh)
        assert np.array_equal(out, fresh)

    def test_reused_and_fresh_placed_in_chunk_order(self):
        old = _chunks([("a_c000", "t1", "b1"), ("b_c000", "t2", "b2")])
        cached = index_frame(plan_incremental(old, cached_index=None))
        cached_matrix = np.array([[10.0, 10.0], [20.0, 20.0]], dtype=np.float32)
        # reorder + one new chunk at the end
        new = _chunks([("b_c000", "t2", "b2"), ("a_c000", "t1", "b1"), ("z_c000", "t9", "b9")])
        plan = plan_incremental(new, cached_index=cached)
        fresh = np.array([[99.0, 99.0]], dtype=np.float32)  # only z_c000
        out = assemble_matrix(plan, cached_matrix=cached_matrix, fresh=fresh)
        expected = np.array(
            [[20.0, 20.0], [10.0, 10.0], [99.0, 99.0]], dtype=np.float32
        )
        assert np.array_equal(out, expected)

    def test_all_reused_empty_fresh(self):
        df = _chunks([("a_c000", "t1", "b1")])
        cached = index_frame(plan_incremental(df, cached_index=None))
        cached_matrix = np.array([[7.0, 7.0]], dtype=np.float32)
        plan = plan_incremental(df, cached_index=cached)
        fresh = np.empty((0, 2), dtype=np.float32)
        out = assemble_matrix(plan, cached_matrix=cached_matrix, fresh=fresh)
        assert np.array_equal(out, cached_matrix)


class TestIndexFrame:
    def test_columns_and_length(self):
        df = _chunks([("a_c000", "t1", "b1"), ("b_c000", "t2", "b2")])
        plan = plan_incremental(df, cached_index=None)
        idx = index_frame(plan)
        assert list(idx.columns) == ["chunk_id", "text_sha1"]
        assert len(idx) == 2
        assert idx["chunk_id"].tolist() == ["a_c000", "b_c000"]
