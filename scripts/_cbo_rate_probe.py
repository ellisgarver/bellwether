"""Throwaway: measure Internet Archive's REAL replay throttle for CBO snapshots.

_REQUEST_SPACING_S=12 was calibrated against the 2026-06-09 "died at pub/41672,
~170 pids in" runs — but all three died at the SAME pid, which is the signature
of a frozen archived-429 block page (the 2026-06-11 stale-cache incident, now
handled by the x-archive-orig-* skip in _wayback_get), NOT a rolling-window rate
ban. So 12s may be wildly over-conservative. This probes the actual ceiling.

Fetches real latest-ts snapshots (the id_ raw endpoint the walk uses) at
escalating paces, using RAW requests (no retry/backoff, so we see IA's true
response), and classifies each:

  - 200/404         -> not throttled (real response)
  - LIVE 429        -> IA throttle: has Retry-After, NO x-archive-orig-* headers
  - archived 429    -> frozen captured block page (x-archive-orig-*) — harmless,
                       the walk skips these; NOT a throttle signal
  - 5xx / reset     -> IA edge under burst (soft signal)

Stops the instant a LIVE 429 appears and reports the fastest clean tier.
~3-4 min total. Run on the RCC login node after `git pull`:

    python scripts/_cbo_rate_probe.py
"""
from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

import requests

from mnd.ingestion.institutional import CBOIngestor

logging.getLogger("mnd").setLevel(logging.WARNING)

CKPT = Path("data/raw/articles/.cbo_2010-01-01_2026-06-11_checkpoint.txt")
UA = CBOIngestor._UA
SNAP = "https://web.archive.org/web/{ts}id_/{url}"
TIERS = [(3.0, 12), (1.5, 12), (0.75, 15), (0.3, 20)]  # (spacing_s, n_requests)


def _classify(resp: requests.Response) -> str:
    if resp.status_code == 429:
        archived = any(k.lower().startswith("x-archive-orig-") for k in resp.headers)
        return "ARCHIVED-429" if archived else "LIVE-429"
    if resp.status_code in (200, 404):
        return "ok"
    if resp.status_code >= 500:
        return f"5xx({resp.status_code})"
    return f"http{resp.status_code}"


def main() -> None:
    ing = CBOIngestor(checkpoint_path=CKPT)
    cdx = ing._build_or_load_cdx_map(date(2010, 1, 1), date(2026, 6, 11))
    # Highest-id pids = most likely real 2010+ content pages (true 200s).
    pool = sorted(cdx)[-200:]

    print(f"\nProbing IA replay throttle over {sum(n for _, n in TIERS)} real "
          f"snapshot fetches across {len(TIERS)} paces.\n"
          f"(current production pace = {CBOIngestor._REQUEST_SPACING_S}s)\n")

    i = 0
    stop = False
    for spacing, n in TIERS:
        counts: dict[str, int] = {}
        elapsed: list[float] = []
        print(f"--- tier: {spacing}s spacing, {n} requests "
              f"({1/spacing:.2f} req/s) ---")
        for _ in range(n):
            pid = pool[i % len(pool)]
            i += 1
            _earliest, latest = cdx[pid]
            url = SNAP.format(ts=latest, url=f"https://www.cbo.gov/publication/{pid}")
            t0 = time.time()
            try:
                resp = requests.get(url, headers={"User-Agent": UA}, timeout=(10, 90))
                dt = time.time() - t0
                kind = _classify(resp)
                ra = resp.headers.get("Retry-After")
            except Exception as exc:
                dt = time.time() - t0
                kind = f"ERR({type(exc).__name__})"
                ra = None
            counts[kind] = counts.get(kind, 0) + 1
            elapsed.append(dt)
            if kind == "LIVE-429":
                print(f"  pub/{pid}: LIVE-429  Retry-After={ra}  "
                      f"-> IA throttle hit at {1/spacing:.2f} req/s")
                stop = True
                break
            time.sleep(spacing)
        avg = sum(elapsed) / len(elapsed) if elapsed else 0.0
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  -> {summary}  | avg fetch {avg:.2f}s\n")
        if stop:
            break

    print("===== VERDICT =====")
    if stop:
        print("A LIVE IA 429 appeared — back off to the last clean tier above.")
    else:
        fastest = TIERS[-1][0]
        print(f"No live 429 at any tier down to {fastest}s ({1/fastest:.2f} req/s).")
        print(f"12s production pace looks over-conservative; "
              f"a {fastest}-1.5s pace cuts the ~84h walk to ~{int(25176*fastest/3600)}"
              f"-{int(25176*1.5/3600)}h.")
    print("(ARCHIVED-429s are frozen block pages the walk already skips — "
          "not a throttle signal.)\n")


if __name__ == "__main__":
    main()
