"""Unit tests for the weekly-update per-source delta windows (ADR-063)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from run_pipeline import BASIS_SET_SOURCES, _source_delta_windows  # noqa: E402


def test_basis_set_has_twelve_sources():
    assert len(BASIS_SET_SOURCES) == 12
    assert "federalreserve" in BASIS_SET_SOURCES and "nber" in BASIS_SET_SOURCES


def test_each_source_advances_from_its_own_frontier_minus_buffer():
    df = pd.DataFrame({
        "source_id": ["imf", "imf", "bis"],
        "published_at": ["2026-06-01T00:00:00Z", "2026-06-20T00:00:00Z", "2026-05-15T00:00:00Z"],
    })
    w = dict((s, (a, b)) for s, a, b in
             _source_delta_windows(df, ("imf", "bis"), 14, "2026-07-04", "2010-01-01"))
    assert w["imf"] == ("2026-06-06", "2026-07-04")   # 06-20 minus 14d
    assert w["bis"] == ("2026-05-01", "2026-07-04")   # 05-15 minus 14d


def test_source_with_no_articles_starts_at_full_start():
    df = pd.DataFrame({"source_id": ["imf"], "published_at": ["2026-06-20T00:00:00Z"]})
    w = dict((s, (a, b)) for s, a, b in
             _source_delta_windows(df, ("imf", "cbo"), 14, "2026-07-04", "2010-01-01"))
    assert w["cbo"] == ("2010-01-01", "2026-07-04")   # never captured


def test_empty_corpus_all_sources_full_start():
    w = _source_delta_windows(pd.DataFrame(), ("imf", "bis"), 14, "2026-07-04", "2010-01-01")
    assert all(start == "2010-01-01" and end == "2026-07-04" for _, start, end in w)


def test_date_only_published_at_is_handled():
    df = pd.DataFrame({"source_id": ["nber"], "published_at": ["2026-06-25"]})
    (_, start, end), = _source_delta_windows(df, ("nber",), 14, "2026-07-04", "2010-01-01")
    assert start == "2026-06-11" and end == "2026-07-04"
