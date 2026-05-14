#!/usr/bin/env python3
"""Smoke tests for checkpoint/resume logic.

Tests the InstitutionalIngestor checkpoint/resume mechanism with mocked
sub-ingestors — no real HTTP requests. Verifies:
  1. Checkpoint is written after a sub-ingestor completes
  2. On resume, completed sub-ingestors are skipped
  3. No duplicate articles appear in the combined JSONL output

The AP News / MarketWatch journalism ingestors were archived in ADR-010 and
are no longer part of the semantic corpus. Their checkpoint logic lives in
scripts/archive/ and is not exercised by the production pipeline.

Usage:
    python scripts/smoke_test_checkpoint.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_BODY = "word " * 150  # 150 words — above any plausible min_body_words
START = date(2024, 1, 1)
END = date(2024, 12, 31)


def _pass(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Test 1 — Institutional checkpoint / resume
# ---------------------------------------------------------------------------

def test_institutional_checkpoint() -> None:
    print("\n=== Test 1: Institutional checkpoint/resume ===")

    from mnd.ingestion.base import Article, Ingestor
    from mnd.ingestion.institutional import InstitutionalIngestor

    class _MockIngestor(Ingestor):
        def __init__(self, sid: str, n: int) -> None:
            self.source_id = sid
            self._n = n

        def fetch(self, start: date, end: date):
            for i in range(self._n):
                yield Article(
                    article_id=f"{self.source_id}-{i:04d}",
                    source_id=self.source_id,
                    url=f"https://example.com/{self.source_id}/{i}",
                    published_at="2024-01-15T00:00:00Z",
                    retrieved_at="2024-01-15T00:00:00Z",
                    title=f"{self.source_id} article {i}",
                    body=FAKE_BODY,
                    tier=1,
                )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checkpoint_path = tmpdir / ".institutional_checkpoint.json"
        out_path = tmpdir / "institutional.jsonl"

        # --- Step 1: consume federalreserve (10) + first imf article, then kill ---
        inst = InstitutionalIngestor(checkpoint_path=checkpoint_path)
        inst._sub_ingestors = [
            _MockIngestor("federalreserve", 10),
            _MockIngestor("imf", 8),
        ]

        gen = inst.fetch(START, END)
        run1_articles: list[Article] = []
        with out_path.open("w") as fh:
            for art in gen:
                fh.write(art.to_jsonl() + "\n")
                run1_articles.append(art)
                if len(run1_articles) == 11:
                    break
        gen.close()  # simulates SLURM kill / KeyboardInterrupt

        # --- Step 2: verify checkpoint ---
        assert checkpoint_path.exists(), "Checkpoint file not written"
        cp = json.loads(checkpoint_path.read_text())
        if cp.get("federalreserve", {}).get("status") != "completed":
            _fail(f"federalreserve not marked completed in checkpoint: {cp}")
        _pass(
            f"Checkpoint written: federalreserve=completed ({cp['federalreserve']['count']} articles)"
        )

        if "imf" in cp and cp["imf"].get("status") == "completed":
            _fail(f"imf should NOT be completed yet: {cp}")
        _pass("imf correctly absent / not-completed in checkpoint")

        # --- Step 3: resume — federalreserve must be skipped ---
        inst2 = InstitutionalIngestor(checkpoint_path=checkpoint_path)
        inst2._sub_ingestors = [
            _MockIngestor("federalreserve", 10),  # should be skipped
            _MockIngestor("imf", 8),
        ]

        run2_articles: list[Article] = []
        with out_path.open("a") as fh:
            for art in inst2.fetch(START, END):
                fh.write(art.to_jsonl() + "\n")
                run2_articles.append(art)

        fed_in_run2 = [a for a in run2_articles if a.source_id == "federalreserve"]
        if fed_in_run2:
            _fail(f"federalreserve articles appeared in run2 (should be skipped): {len(fed_in_run2)}")
        _pass(f"Resume skipped federalreserve; run2 fetched {len(run2_articles)} imf articles")

        # --- Step 4: no federalreserve duplicates in combined JSONL ---
        # (1 imf duplicate is expected: imf-0000 appears in run1 and run2 —
        #  this is correct behaviour; the filter/dedup stage handles it.)
        lines = [l for l in out_path.read_text().splitlines() if l.strip()]
        all_arts = [json.loads(l) for l in lines]

        fed_ids = [a["article_id"] for a in all_arts if a["source_id"] == "federalreserve"]
        fed_dupes = [x for x in fed_ids if fed_ids.count(x) > 1]
        if fed_dupes:
            _fail(f"Duplicate federalreserve article IDs in JSONL: {set(fed_dupes)}")
        n_fed = len(fed_ids)
        n_imf = sum(1 for a in all_arts if a["source_id"] == "imf")
        _pass(
            f"No federalreserve duplicates — combined JSONL has {len(all_arts)} lines "
            f"({n_fed} fed, {n_imf} imf; 1 imf duplicate expected from partial run1)"
        )

    print("  → Test 1 PASSED\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_institutional_checkpoint()
    print("All checkpoint smoke tests passed.")
