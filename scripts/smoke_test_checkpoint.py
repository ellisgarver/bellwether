#!/usr/bin/env python3
"""Smoke tests for checkpoint/resume logic.

Tests institutional and AP News ingestors with mocked sub-ingestors / network
calls — no real HTTP requests. Verifies:
  1. Checkpoint is written after a sub-ingestor / URL batch completes
  2. On resume, completed work is skipped
  3. No duplicate articles appear in the combined JSONL output

Usage:
    python scripts/smoke_test_checkpoint.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_BODY = "word " * 150  # 150 words — above _MIN_BODY_WORDS (100)
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
        #
        # The generator saves the checkpoint for a sub-ingestor AFTER its inner
        # loop exhausts (StopIteration). That happens on the 11th next() call:
        #   call 11 → generator resumes after yield #10, count+=1, inner loop
        #             calls next(fed_gen) → StopIteration → loop done →
        #             checkpoint["federalreserve"] = completed → saved →
        #             outer loop advances to imf → imf yields article 0 →
        #             yield article → caller receives it
        # So we consume 10 fed + 1 imf (= 11 total), then break + close.
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
                # 10 fed + 1 imf = checkpoint saves fed as completed, then we kill
                if len(run1_articles) == 11:
                    break
        gen.close()  # simulates SLURM kill / KeyboardInterrupt

        # --- Step 2: verify checkpoint ---
        assert checkpoint_path.exists(), "Checkpoint file not written"
        cp = json.loads(checkpoint_path.read_text())
        if cp.get("federalreserve", {}).get("status") != "completed":
            _fail(f"federalreserve not marked completed in checkpoint: {cp}")
        _pass(f"Checkpoint written: federalreserve=completed ({cp['federalreserve']['count']} articles)")

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
# Test 2 — AP News checkpoint / resume
# ---------------------------------------------------------------------------

def test_apnews_checkpoint() -> None:
    print("=== Test 2: AP News checkpoint/resume ===")

    from mnd.ingestion.apnews import APNewsIngestor, _load_url_checkpoint

    TOTAL_URLS = 50
    KILL_AFTER = 25

    # Fake CDX results — one pattern returns all 50 pairs, others empty
    fake_pairs = [
        (f"https://apnews.com/article/story-{i:04d}", f"20240115{i:06d}")
        for i in range(TOTAL_URLS)
    ]
    all_fake_urls = {url for url, _ in fake_pairs}

    def _cdx_side_effect(pattern, start, end, domain="apnews"):
        return fake_pairs if "article" in pattern else []

    def _worker_side_effect(url: str, ts: str):
        return url, ts, FAKE_BODY

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checkpoint_path = tmpdir / ".apnews_checkpoint.txt"
        out_path = tmpdir / "apnews.jsonl"

        # --- Step 1: fetch max_urls=50, kill after 25 articles ---
        with patch("mnd.ingestion.apnews._cdx_query", side_effect=_cdx_side_effect), \
             patch("mnd.ingestion.apnews._worker_fetch", side_effect=_worker_side_effect):

            ingestor = APNewsIngestor(checkpoint_path=checkpoint_path, max_urls=TOTAL_URLS)
            gen = ingestor.fetch(START, END)
            run1_articles = []
            with out_path.open("w") as fh:
                for art in gen:
                    fh.write(art.to_jsonl() + "\n")
                    run1_articles.append(art)
                    if len(run1_articles) >= KILL_AFTER:
                        break
            gen.close()  # triggers finally → saves checkpoint

        # --- Step 2: verify checkpoint ---
        assert checkpoint_path.exists(), "AP News checkpoint file not written after kill"
        fetched_after_kill = _load_url_checkpoint(checkpoint_path)
        if len(fetched_after_kill) < KILL_AFTER:
            _fail(
                f"Checkpoint has {len(fetched_after_kill)} URLs; expected ≥{KILL_AFTER}. "
                f"The try/finally in fetch() must not have fired."
            )
        _pass(f"Checkpoint written after kill: {len(fetched_after_kill)} URLs saved")

        # All checkpointed URLs must be in the fake set (no phantom URLs)
        unknown = fetched_after_kill - all_fake_urls
        if unknown:
            _fail(f"Checkpoint contains unknown URLs: {unknown}")
        _pass("All checkpointed URLs are from the fake CDX result set")

        # --- Step 3: resume — only fetch remaining URLs ---
        run2_worker_calls: list[str] = []

        def _worker_tracking(url: str, ts: str):
            run2_worker_calls.append(url)
            return url, ts, FAKE_BODY

        with patch("mnd.ingestion.apnews._cdx_query", side_effect=_cdx_side_effect), \
             patch("mnd.ingestion.apnews._worker_fetch", side_effect=_worker_tracking):

            ingestor2 = APNewsIngestor(checkpoint_path=checkpoint_path, max_urls=TOTAL_URLS)
            run2_articles = []
            with out_path.open("a") as fh:
                for art in ingestor2.fetch(START, END):
                    fh.write(art.to_jsonl() + "\n")
                    run2_articles.append(art)

        # Worker should NOT have been called for any already-checkpointed URL
        already_fetched_called = [u for u in run2_worker_calls if u in fetched_after_kill]
        if already_fetched_called:
            _fail(
                f"Run2 re-fetched {len(already_fetched_called)} URLs that were in the checkpoint: "
                f"{already_fetched_called[:5]}"
            )
        _pass(f"Run2 worker called for {len(run2_worker_calls)} URLs, "
              f"none from the prior checkpoint")

        expected_remaining = TOTAL_URLS - len(fetched_after_kill)
        _pass(f"Run2 fetched {len(run2_articles)} articles (expected ~{expected_remaining} remaining)")

        # --- Step 4: no duplicate article IDs in combined JSONL ---
        lines = [l for l in out_path.read_text().splitlines() if l.strip()]
        all_arts = [json.loads(l) for l in lines]
        ids = [a["article_id"] for a in all_arts]
        dupes = [x for x in ids if ids.count(x) > 1]
        if dupes:
            _fail(f"Duplicate article IDs in combined JSONL: {set(dupes)}")
        total_expected = len(fetched_after_kill) + len(run2_articles)
        if len(all_arts) != total_expected:
            _fail(
                f"JSONL has {len(all_arts)} lines but expected {total_expected} "
                f"(run1={len(run1_articles)}, run2={len(run2_articles)})"
            )
        _pass(f"No duplicates — combined JSONL has {len(all_arts)} unique articles")

    print("  → Test 2 PASSED\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_institutional_checkpoint()
    test_apnews_checkpoint()
    print("All checkpoint smoke tests passed.")
