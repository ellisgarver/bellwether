"""Smoke tests for the Phase 0 scaffold.

These tests are deliberately minimal — they verify that the static scaffold
is internally consistent. Heavier integration tests for ingestion, embedding,
and pipeline execution belong in subsequent phases.

Run from the repo root: `pytest`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Config loading & schema
# ---------------------------------------------------------------------------

def test_master_config_loads():
    from mnd.utils.config import load_config
    cfg = load_config()
    assert cfg["schema_version"] == "1.0.0"
    assert cfg["temporal"]["historical_start"] == "2010-01-01"
    assert cfg["temporal"]["train_test_split"] == "2020-01-01"


def test_embedding_single_model_strategy():
    """ADR-010: single model (all-mpnet-base-v2) — two-model strategy superseded."""
    from mnd.utils.config import load_config
    cfg = load_config()
    assert "primary" in cfg["embedding"]
    assert "comparator" not in cfg["embedding"], "comparator slot removed in ADR-010"
    assert "mpnet" in cfg["embedding"]["primary"]["model"]
    assert cfg["embedding"]["primary"]["dimensions"] == 768


def test_kill_criteria_thresholds_present():
    """Kill criteria thresholds must be in config (not hardcoded)."""
    from mnd.utils.config import load_config
    cfg = load_config()
    assert cfg["dynamics"]["min_r_squared"] == 0.30
    assert cfg["dynamics"]["max_r0_ci_width"] == 2.0
    assert cfg["validation"]["required_anchors_recovered"] == 7
    assert cfg["validation"]["min_bootstrap_nmi"] == 0.40


def test_random_seed_pinned():
    from mnd.utils.config import load_config
    cfg = load_config()
    assert cfg["reproducibility"]["global_random_seed"] == 42


# ---------------------------------------------------------------------------
# Whitelist + keywords
# ---------------------------------------------------------------------------

def test_whitelist_loads_and_has_required_outlets():
    from mnd.utils.config import load_yaml
    wl = load_yaml("config/whitelist.yaml")
    # ADR-010: journalism tier removed; three-tier institutional+academic corpus
    assert "tier_1_institutional_policy" in wl, "missing tier_1_institutional_policy"
    assert "tier_4_open_journalism" not in wl, "tier_4_open_journalism should not exist (ADR-010)"
    tier_1_ids = {e["id"] for e in wl["tier_1_institutional_policy"]}
    tier_2_ids = {e["id"] for e in wl["tier_2_academic_analytical"]}
    tier_2_policy_ids = {e["id"] for e in wl["tier_2_policy_analytical"]}
    for required in ("fed_board", "imf", "bis"):
        assert required in tier_1_ids, f"missing required tier-1 source: {required}"
    for required in ("voxeu", "arxiv"):
        assert required in tier_2_ids, f"missing required tier-2 academic source: {required}"
    for required in ("brookings", "piie", "cfr"):
        assert required in tier_2_policy_ids, f"missing required tier-2 policy source: {required}"
    # Journalism sources must be absent from all active semantic corpus tiers
    all_active_ids = tier_1_ids | tier_2_ids | tier_2_policy_ids
    for removed in ("apnews", "reuters", "marketwatch"):
        assert removed not in all_active_ids, f"{removed} should not be in semantic corpus (ADR-010)"


def test_keyword_seed_has_minimum_coverage():
    from mnd.utils.config import load_yaml
    kw = load_yaml("config/topic_filter_keywords.yaml")
    n = sum(len(v) for v in kw["categories"].values())
    assert n >= 100, f"keyword set looks thin: only {n} terms"


# ---------------------------------------------------------------------------
# Anchor narratives
# ---------------------------------------------------------------------------

def test_anchor_narratives_jsonl_well_formed():
    path = REPO / "data" / "anchors" / "anchor_narratives.jsonl"
    assert path.exists(), f"missing {path}"
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(records) == 10, f"expected 10 anchor narratives, got {len(records)}"
    required = {"id", "name", "category", "reference_date", "tolerance_days", "key_terms",
                "expected_emergence_speed", "why_anchor", "expected_significance_threshold"}
    for r in records:
        missing = required - set(r.keys())
        assert not missing, f"anchor {r.get('id')} missing fields: {missing}"
    # IDs are unique
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate anchor IDs"


def test_fizzled_seed_marked_as_draft():
    """Fizzled counterparts MUST be marked DRAFT until corpus-confirmed."""
    path = REPO / "data" / "anchors" / "fizzled_counterparts_seed.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(records) >= 3
    for r in records:
        assert r.get("_seed_status", "").startswith("DRAFT"), (
            f"fizzled candidate {r.get('id')} must be DRAFT until corpus-confirmed"
        )


# ---------------------------------------------------------------------------
# Ingestor instantiation
# ---------------------------------------------------------------------------

def test_ingestors_importable():
    # ADR-010: institutional+academic corpus only; journalism ingestors archived
    from mnd.ingestion import (
        Article,
        FederalReserveIngestor,
        FredFetcher,
        InstitutionalIngestor,
        Ingestor,
    )
    assert issubclass(InstitutionalIngestor, Ingestor)
    assert issubclass(FederalReserveIngestor, Ingestor)
    # Article is a dataclass with the canonical fields
    a = Article(
        article_id="x", source_id="fed_board", url="https://federalreserve.gov/x",
        published_at="2024-01-01T00:00:00Z", retrieved_at="2024-01-01T00:00:00Z",
        title="t",
    )
    assert a.tier == 1


def test_cfr_ingestor_importable():
    """ADR-010: CFR reinstated as Tier 2 source."""
    from mnd.ingestion.institutional import CFRIngestor
    from mnd.ingestion.base import Ingestor
    assert issubclass(CFRIngestor, Ingestor)
    assert CFRIngestor.source_id == "cfr"


def test_mediacloud_detector_importable():
    """ADR-010: Media Cloud detection layer added."""
    from mnd.detection.mediacloud import MediaCloudDetector
    assert hasattr(MediaCloudDetector, "fetch_story_counts")
    assert hasattr(MediaCloudDetector, "detect_anomalies")


# ---------------------------------------------------------------------------
# Embedding module shape (no model load)
# ---------------------------------------------------------------------------

def test_embedder_factory_produces_correct_config():
    """ADR-010: single model all-mpnet-base-v2."""
    from mnd.embedding import Embedder
    primary = Embedder.from_config("primary")
    assert "mpnet" in primary.model_name
    assert primary.instruction_aware is False
    assert primary.max_seq_len == 384
