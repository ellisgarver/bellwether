#!/usr/bin/env python
"""THROWAWAY probe — measure Internet Archive's Wayback rate limit for CBO.

Not part of the pipeline. Answers three questions with data instead of guesses,
so we can set the CBO ingest pacing from IA's actual behavior:

  1. BURST TOLERANCE — how many back-to-back replay GETs succeed before the
     first HTTP 429?
  2. Retry-After — does IA send the header on its 429, and what value?
  3. COOLDOWN — once blocked, how long until a request succeeds again?

It reuses CBOIngestor's CDX machinery to gather REAL snapshot URLs (the exact
endpoint the ingest hits), then fires bare requests.get (NOT _wayback_get, whose
retries would mask the raw 429 signal).

Usage on RCC (single line):
  python scripts/_probe_wayback_rate.py --delay 0.3 --n 600

Delete this file once the pacing is set.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import requests

# Bootstrap: make `mnd` importable whether or not it's pip-installed.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mnd.ingestion.institutional import CBOIngestor  # noqa: E402


def gather_snapshot_urls(want: int) -> list[str]:
    """Collect `want` real CBO snapshot replay URLs via CDX block queries."""
    ing = CBOIngestor()
    id_lo, id_hi = ing._estimate_id_range(date(2010, 1, 1), date(2026, 6, 8))
    urls: list[str] = []
    for prefix in range(id_lo // 100, id_hi // 100 + 1):
        try:
            block = list(ing._cdx_block(prefix))
        except Exception as exc:  # CDX is a separate, higher limit; tolerate here
            print(f"  [cdx] block {prefix}* failed: {exc} — skipping")
            continue
        for pid, _earliest_ts, latest_ts in block:
            original = f"https://www.cbo.gov/publication/{pid}"
            urls.append(ing._SNAP_PREFIX.format(ts=latest_ts, url=original))
            if len(urls) >= want:
                return urls
        print(f"  [cdx] block {prefix}* → {len(block)} snapshots "
              f"(total {len(urls)}/{want})")
        time.sleep(0.5)
    return urls


def count_publications() -> int:
    """CDX-only enumeration: how many unique CBO pids must the walk fetch?

    Hits only the CDX endpoint (separate, higher limit than replay) via the
    ingestor's own retry-cushioned ``_cdx_block``, so it does not spend the
    replay-GET budget. Reports the unique-pid total, a per-year histogram (by
    earliest-snapshot date as a rough proxy), and walltime estimates at the
    measured safe rate — the number that decides whether the Wayback walk is
    feasible within QOS or needs a different sourcing strategy.
    """
    ing = CBOIngestor()
    id_lo, id_hi = ing._estimate_id_range(date(2010, 1, 1), date(2026, 6, 8))
    blocks = range(id_lo // 100, id_hi // 100 + 1)
    print(f"Counting unique CBO pids over ids [{id_lo}..{id_hi}] "
          f"({len(blocks)} CDX blocks). CDX-only, no replay GETs.\n")
    pids: set[int] = set()
    by_year: dict[int, int] = {}
    for n, prefix in enumerate(blocks, start=1):
        try:
            block = list(ing._cdx_block(prefix))
        except Exception as exc:
            print(f"  [cdx] block {prefix}* FAILED: {exc} — skipping")
            continue
        for pid, earliest_ts, _latest_ts in block:
            if pid in pids:
                continue
            pids.add(pid)
            d = ing._ts_to_date(earliest_ts)
            y = d.year if d else 0
            by_year[y] = by_year.get(y, 0) + 1
        if n % 10 == 0 or n == len(blocks):
            print(f"  block {prefix}* ({n}/{len(blocks)}) — {len(pids)} unique pids so far")
        time.sleep(1.0)

    total = len(pids)
    print("\n" + "=" * 60)
    print("CBO PUBLICATION COUNT")
    print("=" * 60)
    print(f"  Unique pids to fetch: {total}")
    print("  Per-year (by earliest snapshot date, rough proxy):")
    for y in sorted(by_year):
        label = "unknown" if y == 0 else str(y)
        print(f"    {label}: {by_year[y]}")
    print(f"\n  Walltime @ 1 req/12s (steady safe rate): {total * 12 / 3600:.1f}h")
    print(f"  Walltime @ burst-15-then-185s-sleep      : {total / 15 * 185 / 3600:.1f}h")
    print(f"  caslake QOS cap is 36h — feasible if under that.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.3,
                    help="seconds between burst requests (default 0.3 = current ingest pace)")
    ap.add_argument("--n", type=int, default=300,
                    help="max burst requests before declaring the rate tolerated")
    ap.add_argument("--poll", type=float, default=30.0,
                    help="seconds between gentle polls in the cooldown/unban phases")
    ap.add_argument("--cap", type=float, default=1800.0,
                    help="give up waiting for a block to clear after this many seconds")
    ap.add_argument("--count", action="store_true",
                    help="CDX-only: count unique CBO pids + per-year histogram (no replay GETs), "
                         "then estimate walltime at the safe rate. Use this to decide feasibility.")
    args = ap.parse_args()

    if args.count:
        return count_publications()

    headers = {"User-Agent": CBOIngestor._UA}
    timeout = (10, 30)

    def probe_once(url: str) -> tuple[str, str]:
        """Return ('ok'|'blocked'|'other', detail) for one GET.

        A connection refusal / reset / timeout AND HTTP 429/503 all count as
        'blocked' — IA throttles at both the TCP and HTTP layers.
        """
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except Exception as exc:
            return "blocked", f"net:{type(exc).__name__}"
        if resp.status_code == 200:
            return "ok", "200"
        if resp.status_code in (429, 503):
            return "blocked", f"HTTP {resp.status_code} Retry-After={resp.headers.get('Retry-After')!r}"
        return "other", f"HTTP {resp.status_code}"

    print(f"Gathering up to {args.n + 50} real CBO snapshot URLs from CDX ...")
    urls = gather_snapshot_urls(args.n + 50)
    if len(urls) < 10:
        print(f"FAILED: only gathered {len(urls)} URLs — CDX may be down.")
        return 1
    print(f"Got {len(urls)} URLs.\n")
    idx = 0

    def next_url() -> str:
        nonlocal idx
        u = urls[idx % len(urls)]
        idx += 1
        return u

    # ---- Phase 0: clear any pre-existing ban (gentle, no hammering) -------
    print("=== PHASE 0: ensure we start unblocked (gentle poll) ===")
    waited = 0.0
    while True:
        status, detail = probe_once(next_url())
        if status == "ok":
            print(f"  unblocked after {waited:.0f}s — starting burst.\n")
            break
        print(f"  +{waited:4.0f}s: blocked ({detail}) — waiting {args.poll:.0f}s")
        if waited >= args.cap:
            print(f"  CAP HIT: still blocked after {args.cap:.0f}s. IA is banning "
                  "this IP hard. Re-run later, or the base rate must be very low.")
            return 1
        time.sleep(args.poll)
        waited += args.poll

    # ---- Phase 1: burst tolerance ----------------------------------------
    print(f"=== PHASE 1: burst at {args.delay}s/request (≈ {60/args.delay:.0f}/min) ===")
    ok = 0
    consec_block = 0
    block_detail = ""
    t0 = time.time()
    tolerated = True
    for i in range(args.n):
        status, detail = probe_once(next_url())
        if status == "ok":
            ok += 1
            consec_block = 0
        else:
            consec_block += 1
            block_detail = detail
            if consec_block >= 2:  # two in a row = real block, not a single flap
                print(f"  *** BLOCKED after {ok} OK requests in {time.time()-t0:.0f}s "
                      f"({detail}) ***")
                tolerated = False
                break
        if (i + 1) % 10 == 0:
            print(f"  req {i+1:4d}: {ok} OK so far ({time.time()-t0:.0f}s)")
        time.sleep(args.delay)

    if tolerated:
        print(f"\nTOLERATED: {ok} OK in {args.n} requests at {args.delay}s with no "
              "sustained block. This rate is safe — or push --delay lower / --n higher.")
        return 0

    # ---- Phase 2: cooldown — STOP hammering, poll gently until clear ------
    print(f"\n=== PHASE 2: cooldown — polling every {args.poll:.0f}s, NOT hammering "
          f"(cap {args.cap:.0f}s) ===")
    cd = 0.0
    cooldown: float | None = None
    while cd < args.cap:
        time.sleep(args.poll)
        cd += args.poll
        status, detail = probe_once(next_url())
        print(f"  +{cd:5.0f}s: {status} ({detail})")
        if status == "ok":
            cooldown = cd
            break

    # ---- Summary ----------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Burst tolerance : {ok} OK requests before block at {args.delay}s spacing")
    print(f"  Block signal    : {block_detail}")
    if cooldown is not None:
        period = cooldown + ok * args.delay
        print(f"  Cooldown        : block cleared after ~{cooldown:.0f}s of NOT hammering")
        print(f"  → Sustained-safe ≈ {ok} requests per ~{period:.0f}s "
              f"= 1 request / {period/max(ok,1):.1f}s")
    else:
        print(f"  Cooldown        : STILL BLOCKED after {args.cap:.0f}s (cap hit). "
              "IA's ban is long; pace must stay well under the burst threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
