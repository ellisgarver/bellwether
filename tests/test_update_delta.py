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


def test_composite_fed_regional_frontier_uses_sub_source_ids():
    # The corpus stores fed_atlanta/fed_chicago/fed_ny/fed_sf — never
    # "fed_regional" itself — so the composite's frontier must derive from the
    # subs. Before the COMPOSITE_SOURCE_IDS mapping, the lookup always missed
    # and the weekly delta restarted at full_start: a 16-year regional-Fed
    # re-walk every week.
    df = pd.DataFrame({
        "source_id": ["fed_ny", "fed_atlanta", "fed_sf", "fed_chicago"],
        "published_at": ["2026-06-28T00:00:00Z", "2026-05-30T00:00:00Z",
                         "2026-06-20T00:00:00Z", "2026-06-25T00:00:00Z"],
    })
    (_, start, end), = _source_delta_windows(
        df, ("fed_regional",), 14, "2026-07-04", "2010-01-01")
    # min across subs (laggiest = atlanta 05-30) minus 14d: no sub left gapped.
    assert start == "2026-05-16" and end == "2026-07-04"


def test_composite_with_no_sub_articles_still_full_start():
    df = pd.DataFrame({"source_id": ["imf"], "published_at": ["2026-06-20T00:00:00Z"]})
    (_, start, _), = _source_delta_windows(
        df, ("fed_regional",), 14, "2026-07-04", "2010-01-01")
    assert start == "2010-01-01"


def test_update_merge_path_refreshes_pre_embed_corpus_first(monkeypatch):
    # `filter` prefers corpus_for_embedding.jsonl whenever it exists, and the
    # full build leaves a stale copy behind — so the merge path MUST re-run
    # filter-pre-embed before filter, or the weekly delta silently never
    # reaches embed/merge ("no new chunks" forever while the site re-bakes).
    from click.testing import CliRunner

    import run_pipeline as rp

    calls: list[str] = []
    monkeypatch.setattr(rp.filter_pre_embed, "callback",
                        lambda *a, **k: calls.append("filter-pre-embed"))
    monkeypatch.setattr(rp.filter_cmd, "callback",
                        lambda *a, **k: calls.append("filter"))
    monkeypatch.setattr(rp.embed, "callback",
                        lambda *a, **k: calls.append("embed"))
    monkeypatch.setattr(rp.merge_week, "callback",
                        lambda *a, **k: calls.append("merge-week"))
    monkeypatch.setattr(rp.analyze, "callback",
                        lambda *a, **k: calls.append("analyze"))

    result = CliRunner().invoke(rp.cli, ["update", "--skip-ingest", "--merge"])
    assert result.exit_code == 0, result.output
    assert calls == ["filter-pre-embed", "filter", "embed", "merge-week", "analyze"]
