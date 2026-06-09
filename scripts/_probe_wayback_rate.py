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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.3,
                    help="seconds between burst requests (default 0.3 = current ingest pace)")
    ap.add_argument("--n", type=int, default=600,
                    help="max burst requests before giving up looking for a 429")
    ap.add_argument("--cooldown-poll", type=float, default=20.0,
                    help="seconds between cooldown-phase polls")
    ap.add_argument("--cooldown-cap", type=float, default=1800.0,
                    help="give up waiting for the block to clear after this many seconds")
    args = ap.parse_args()

    headers = {"User-Agent": CBOIngestor._UA}
    timeout = (10, 30)

    print(f"Gathering up to {args.n + 50} real CBO snapshot URLs from CDX ...")
    urls = gather_snapshot_urls(args.n + 50)
    if len(urls) < 10:
        print(f"FAILED: only gathered {len(urls)} URLs — CDX may be down.")
        return 1
    print(f"Got {len(urls)} URLs.\n")

    # ---- Phase 1: burst tolerance ----------------------------------------
    print(f"=== PHASE 1: burst at {args.delay}s/request (≈ {60/args.delay:.0f}/min) ===")
    first_429_at: int | None = None
    retry_after: str | None = None
    ok = 0
    other: dict[int, int] = {}
    t0 = time.time()
    for i, url in enumerate(urls[:args.n], start=1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except Exception as exc:
            print(f"  req {i:4d}: NETWORK ERROR {exc}")
            time.sleep(args.delay)
            continue
        code = resp.status_code
        if code == 200:
            ok += 1
        elif code == 429:
            first_429_at = i
            retry_after = resp.headers.get("Retry-After")
            print(f"  req {i:4d}: *** HTTP 429 *** (first throttle) "
                  f"Retry-After={retry_after!r}  after {ok} OK in {time.time()-t0:.0f}s")
            break
        else:
            other[code] = other.get(code, 0) + 1
        if i % 25 == 0:
            print(f"  req {i:4d}: {ok} OK so far ({time.time()-t0:.0f}s elapsed)")
        time.sleep(args.delay)

    if first_429_at is None:
        print(f"\nNo 429 in {args.n} requests at {args.delay}s spacing — "
              f"{ok} OK, others={other}.")
        print("IA tolerated this rate. Try a faster --delay to find the ceiling, "
              "or treat this rate as safe.")
        return 0

    # ---- Phase 2: cooldown duration --------------------------------------
    print(f"\n=== PHASE 2: cooldown — polling every {args.cooldown_poll:.0f}s "
          f"until a 200 returns (cap {args.cooldown_cap:.0f}s) ===")
    if retry_after:
        print(f"  IA's stated Retry-After was {retry_after!r} — measuring actual clear time too.")
    cd_start = time.time()
    poll_url_idx = first_429_at  # use fresh URLs we haven't hit yet
    cleared_at: float | None = None
    while time.time() - cd_start < args.cooldown_cap:
        time.sleep(args.cooldown_poll)
        url = urls[poll_url_idx % len(urls)]
        poll_url_idx += 1
        elapsed = time.time() - cd_start
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            code = resp.status_code
        except Exception as exc:
            print(f"  +{elapsed:5.0f}s: NETWORK ERROR {exc}")
            continue
        print(f"  +{elapsed:5.0f}s: HTTP {code}"
              + (f"  Retry-After={resp.headers.get('Retry-After')!r}" if code == 429 else ""))
        if code == 200:
            cleared_at = elapsed
            break

    # ---- Summary ----------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Burst tolerance : {first_429_at - 1} OK requests before first 429 "
          f"at {args.delay}s spacing")
    print(f"  Retry-After hdr : {retry_after!r}")
    if cleared_at is not None:
        print(f"  Cooldown        : block cleared after ~{cleared_at:.0f}s")
        print(f"  → Sustained-safe rate ≈ {first_429_at - 1} requests per "
              f"{cleared_at:.0f}s = 1 request / {cleared_at/max(first_429_at-1,1):.1f}s")
    else:
        print(f"  Cooldown        : STILL BLOCKED after {args.cooldown_cap:.0f}s "
              "(cap hit) — IA's block is long; the base rate must be well under "
              "the burst threshold to avoid tripping it at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
