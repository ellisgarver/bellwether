"""Empirical calibration probe for CBO via Wayback Machine.

Question this probe answers: of the cbo.gov publication URLs surfaced by
the Wayback CDX API, what fraction yield an authoritative page-extracted
publication date and a substantive body when we fetch the raw snapshot?

Run on RCC (or anywhere with internet) and report the result back. The
decision tree:

  - page_date_yield_pct >= 50% → keep CBOIngestor on the strict Wayback
    path. Coverage will be partial but methodology-clean.
  - page_date_yield_pct < 20%  → pivot. Options to discuss:
      (a) govinfo CBO collection (sparse over time but page-date clean)
      (b) Common Crawl WARC for cbo.gov (free, dense)
      (c) Residential-IP scraping service for cbo.gov direct
      (d) Drop CBO from the basis set (loses fiscal-authority dimension)
  - 20-50%                     → judgment call; lay out trade-offs.

Run::

    python scripts/probe_cbo_wayback_dates.py --window 2023-06-01..2023-07-31 \\
        --sample-size 50

Emits a CSV of (snapshot_ts, original_url, page_date, body_word_count,
date_source, trafilatura_meta_date, fetch_status) and a summary dict.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

# Add src/ to path so this script is runnable from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import requests  # noqa: E402

from mnd.ingestion.institutional import CBOIngestor  # noqa: E402
from mnd.ingestion.trafilatura_fetcher import _fetch_page_full  # noqa: E402


def parse_window(s: str) -> tuple[date, date]:
    start_str, end_str = s.split("..")
    return date.fromisoformat(start_str), date.fromisoformat(end_str)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--window",
        type=str,
        default="2023-06-01..2023-07-31",
        help="Date window YYYY-MM-DD..YYYY-MM-DD (default 2 months in 2023)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of Wayback snapshots to randomly sample and fetch",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sampling (default 42, matches project seed)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/diagnostics/cbo_wayback_calibration.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    start, end = parse_window(args.window)
    print(f"CBO Wayback calibration: window={start}..{end} sample_size={args.sample_size}")

    ingestor = CBOIngestor()
    # 1. Enumerate candidates via the existing CDX path.
    candidates = list(ingestor._enumerate_wayback_candidates(start, end))
    print(f"CDX returned {len(candidates)} unique cbo.gov/publication URLs")
    if not candidates:
        print("Zero candidates — Wayback CDX is empty for this window. Exit.")
        sys.exit(1)

    # 2. Sample uniformly at random.
    rng = random.Random(args.seed)
    sample = rng.sample(candidates, k=min(args.sample_size, len(candidates)))

    # 3. Fetch each, attempt page-date extraction via trafilatura.
    rows: list[dict] = []
    page_date_count = 0
    body_ok_count = 0
    fetch_fail_count = 0
    snapshot_date_misalignment: list[tuple[date, date]] = []
    for i, (original_url, snapshot_ts) in enumerate(sample, 1):
        snap_url = ingestor._SNAP_PREFIX.format(ts=snapshot_ts, url=original_url)
        snapshot_date = CBOIngestor._ts_to_date(snapshot_ts)
        print(f"[{i}/{len(sample)}] {original_url}", flush=True)
        body = ""
        page_date = None
        title = ""
        try:
            body, title, _author, page_date = _fetch_page_full(
                snap_url, min_words=10, getter=ingestor._wayback_get,
            )
        except Exception as exc:
            fetch_fail_count += 1
            rows.append({
                "snapshot_ts": snapshot_ts,
                "original_url": original_url,
                "page_date": "",
                "body_word_count": 0,
                "title": "",
                "snapshot_date": snapshot_date.isoformat() if snapshot_date else "",
                "fetch_status": f"error:{type(exc).__name__}",
            })
            time.sleep(0.3)
            continue
        word_count = len(body.split()) if body else 0
        if page_date is not None:
            page_date_count += 1
            if snapshot_date and abs((snapshot_date - page_date).days) > 365:
                snapshot_date_misalignment.append((snapshot_date, page_date))
        if word_count >= 200:
            body_ok_count += 1
        rows.append({
            "snapshot_ts": snapshot_ts,
            "original_url": original_url,
            "page_date": page_date.isoformat() if page_date else "",
            "body_word_count": word_count,
            "title": title or "",
            "snapshot_date": snapshot_date.isoformat() if snapshot_date else "",
            "fetch_status": "ok" if body else "empty_body",
        })
        time.sleep(0.3)

    # 4. Write CSV.
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "snapshot_ts", "original_url", "page_date", "body_word_count",
                "title", "snapshot_date", "fetch_status",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    # 5. Summary.
    total = len(sample)
    summary = {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "sample_size": total,
        "candidates_total": len(candidates),
        "page_date_yield_pct": round(100.0 * page_date_count / total, 1),
        "body_ok_yield_pct": round(100.0 * body_ok_count / total, 1),
        "fetch_failure_pct": round(100.0 * fetch_fail_count / total, 1),
        "snapshot_pubdate_misalignments_gt_1y": len(snapshot_date_misalignment),
        "csv_path": str(out_path),
        "run_at": datetime.utcnow().isoformat() + "Z",
    }

    print()
    print("=" * 72)
    print("CBO Wayback calibration summary")
    print("=" * 72)
    print(json.dumps(summary, indent=2))
    print()
    print("Decision rules:")
    if summary["page_date_yield_pct"] >= 50:
        print("  → page_date_yield ≥ 50%: KEEP strict Wayback path.")
    elif summary["page_date_yield_pct"] < 20:
        print("  → page_date_yield < 20%: PIVOT off Wayback.")
        print("    Discuss alternatives: govinfo CBO / Common Crawl /")
        print("    residential-IP service / drop CBO from basis set.")
    else:
        print("  → 20% ≤ page_date_yield < 50%: JUDGMENT CALL.")
        print("    Review the CSV for whether the dated records cluster by")
        print("    publication-type (e.g. all blog posts dated, all reports")
        print("    un-dated) — that might admit a type-specific path.")
    print()
    print("Top 10 sample rows by body_word_count:")
    for row in sorted(rows, key=lambda r: r["body_word_count"], reverse=True)[:10]:
        print(
            f"  [{row['page_date'] or '----':10}] "
            f"snap={row['snapshot_date']}  "
            f"body={row['body_word_count']:6}w  "
            f"{row['original_url']}"
        )
    print(f"\nDistribution of fetch_status: {dict(Counter(r['fetch_status'] for r in rows))}")
    if snapshot_date_misalignment:
        print(
            f"\n{len(snapshot_date_misalignment)} of {page_date_count} dated "
            f"records have snapshot date >1y from extracted page date — "
            f"confirms the snapshot-timestamp fallback was unsafe."
        )


if __name__ == "__main__":
    main()
