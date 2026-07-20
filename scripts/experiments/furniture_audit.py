"""Dry-run audit of the furniture cleaner (ADR-082) over the real corpus.

Reads the filter stage's own input the same way ``run_pipeline.py filter`` does
(corpus_for_embedding.jsonl, else raw articles), runs ``FurnitureCleaner`` in
PREVIEW mode — mutating nothing — and reports what WOULD change, per source,
with before/after samples. Nothing is written to the corpus, so this is safe to
run before committing to the irreversible re-embed.

Purpose: confirm the cleaning is appropriate across ALL sources (not just BIS
and PDFs) and catch any over-eager stripping before it reaches the embedder.

Usage (RCC, repo root, venv active):
  python scripts/experiments/furniture_audit.py                 # summary + samples
  python scripts/experiments/furniture_audit.py --samples 8     # more samples/source
  python scripts/experiments/furniture_audit.py --source bis    # focus one source
  python scripts/experiments/furniture_audit.py --json out.json # machine-readable

Reads config.filtering.furniture for the same knobs the real run will use, so
what you see here is exactly what the filter stage will do.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mnd.filtering.furniture import FurnitureCleaner  # noqa: E402
from mnd.utils.config import load_config  # noqa: E402
from mnd.utils.logging import get_logger  # noqa: E402

log = get_logger("furniture_audit")


def _load_articles(cfg) -> list[dict]:
    """Mirror run_pipeline.filter_cmd input precedence, as plain dicts."""
    root = Path(".")
    corpus = root / cfg["paths"]["corpus_for_embedding"]
    raw_dir = root / cfg["paths"]["raw_articles"]
    out: list[dict] = []
    bad = 0

    def _read(path: Path) -> None:
        nonlocal bad
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    bad += 1

    if corpus.exists():
        log.info("Reading %s", corpus)
        _read(corpus)
    elif raw_dir.exists():
        log.info("Reading raw articles from %s", raw_dir)
        for f in sorted(raw_dir.glob("*.jsonl")):
            _read(f)
    else:
        log.error("No corpus_for_embedding.jsonl or raw articles found.")
        sys.exit(1)
    if bad:
        log.warning("Skipped %d unparseable lines", bad)
    return out


def _trunc(s: str, n: int = 160) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=4, help="before/after samples per source")
    ap.add_argument("--source", default=None, help="restrict to one source_id")
    ap.add_argument("--json", default=None, help="write machine-readable report here")
    args = ap.parse_args()

    cfg = load_config()
    cleaner = FurnitureCleaner.from_config(cfg)
    # Preview regardless of the enabled flag — this is a dry run.
    cleaner.enabled = True

    articles = _load_articles(cfg)
    if args.source:
        articles = [a for a in articles if a.get("source_id") == args.source]
    log.info("Auditing %d articles", len(articles))

    per_source = defaultdict(lambda: {
        "n": 0, "byline": 0, "preamble": 0, "leading": 0, "furniture_lines": 0,
        "reference": 0, "modified": 0, "chars_before": 0, "chars_removed": 0,
    })
    samples = defaultdict(list)

    for a in articles:
        src = str(a.get("source_id") or "?")
        title = str(a.get("title") or "")
        body = str(a.get("body") or "")
        s = per_source[src]
        s["n"] += 1
        s["chars_before"] += len(body)

        new_title, new_body, speaker, d = cleaner.clean_one(title, body, src)
        modified = speaker is not None or d["preamble"] or d["leading"] or d["furniture_lines"]
        s["byline"] += int(speaker is not None)
        s["preamble"] += d["preamble"]
        s["leading"] += d["leading"]
        s["furniture_lines"] += d["furniture_lines"]
        s["reference"] += d["reference"]
        s["chars_removed"] += max(0, len(body) - len(new_body))
        if modified:
            s["modified"] += 1
            if len(samples[src]) < args.samples:
                samples[src].append({
                    "title_before": _trunc(title, 90),
                    "title_after": _trunc(new_title, 90),
                    "speaker": speaker,
                    "leading": bool(d["leading"]),
                    "body_head_before": _trunc(body, 200),
                    "body_head_after": _trunc(new_body, 200),
                    "lines_dropped": d["furniture_lines"],
                    "reference_tail": bool(d["reference"]),
                })

    # ---- report ----
    print("\n=== Furniture audit (dry run) — per source ===")
    hdr = (f"{'source':<18}{'docs':>7}{'modif':>7}{'byline':>7}{'pre':>6}"
           f"{'lead':>6}{'lines':>8}{'ref':>6}{'%chars':>8}")
    print(hdr)
    print("-" * len(hdr))
    for src in sorted(per_source, key=lambda s: -per_source[s]["n"]):
        s = per_source[src]
        pct = 100.0 * s["chars_removed"] / max(s["chars_before"], 1)
        print(f"{src:<18}{s['n']:>7}{s['modified']:>7}{s['byline']:>7}"
              f"{s['preamble']:>6}{s['leading']:>6}{s['furniture_lines']:>8}"
              f"{s['reference']:>6}{pct:>7.1f}%")

    print("\n=== Samples (before → after) ===")
    for src in sorted(samples):
        print(f"\n--- {src} ---")
        for ex in samples[src]:
            if ex["speaker"]:
                print(f"  TITLE: {ex['title_before']!r}")
                print(f"      →  {ex['title_after']!r}   [speaker: {ex['speaker']}]")
            if ex["leading"] or ex["lines_dropped"] or ex["reference_tail"]:
                tag = []
                if ex["leading"]:
                    tag.append("leading")
                if ex["lines_dropped"]:
                    tag.append(f"{ex['lines_dropped']} lines")
                if ex["reference_tail"]:
                    tag.append("ref tail")
                print(f"  BODY ({', '.join(tag)}):")
                print(f"      before: {ex['body_head_before']!r}")
                print(f"      after:  {ex['body_head_after']!r}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"per_source": per_source, "samples": samples}, indent=2, default=str))
        log.info("Wrote machine-readable report → %s", args.json)

    print("\nNothing was written to the corpus. Review the samples above; if the "
          "cleaning looks right, proceed with the filter → embed → cluster chain.")


if __name__ == "__main__":
    main()
