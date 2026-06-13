"""Throwaway CBO resume-sanity probe (not part of the pipeline).

Job 50724243 timed out with 5879 pids marked done in the checkpoint but ZERO
articles in the output JSONL. Before burning another 36h resume we must know
whether that 0-kept is legitimate (low pid band = pre-2010 content, dropped
out-of-window) or a systematic extraction failure (every Wayback fetch hitting
the interstitial / no page-date → everything silently dropped at log.debug).

This loads the already-built CDX cache (no re-enumeration), samples pids across
the done (low) and not-done (high) bands, fetches each through the real
_fetch_and_build, and tabulates kept vs drop-reason with the extracted page_date.
~16 fetches at the 12s IA-safe pace stays well under the replay-ban threshold.

Run on the RCC login node after `git pull`:
    python scripts/_cbo_resume_probe.py
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

from mnd.ingestion.institutional import CBOIngestor

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-7s | %(name)s | %(message)s",
)


class _Capture(logging.Handler):
    """Buffer mnd.* log records so each pid's drop reason can be shown inline."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.msgs: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.msgs.append(record.getMessage())


_CAP = _Capture()
# mnd's logger pins itself to INFO (utils.logging._configure_root); force DEBUG
# so _fetch_and_build's per-drop debug lines actually reach the capture handler.
logging.getLogger("mnd").setLevel(logging.DEBUG)
logging.getLogger("mnd").addHandler(_CAP)

CKPT = Path(
    sys.argv[1] if len(sys.argv) > 1
    else "data/raw/articles/.cbo_2010-01-01_2026-06-11_checkpoint.txt"
)
START, END = date(2010, 1, 1), date(2026, 6, 11)
N_DONE_SAMPLES = 4      # confirm the done band is genuinely pre-window
N_TODO_SAMPLES = 12     # what the resume will actually process next


def _spread(seq: list[int], k: int) -> list[int]:
    if len(seq) <= k:
        return list(seq)
    step = len(seq) / k
    return [seq[int(i * step)] for i in range(k)]


def main() -> None:
    ing = CBOIngestor(checkpoint_path=CKPT)
    cdx = ing._build_or_load_cdx_map(START, END)  # loads cache, no sweep
    done = ing._done_pids
    all_pids = sorted(cdx)
    done_pids = [p for p in all_pids if p in done]
    todo_pids = [p for p in all_pids if p not in done]

    print(f"\nCDX cache: {len(all_pids)} pids (ids {all_pids[0]}..{all_pids[-1]})")
    print(f"checkpoint done: {len(done_pids)}  |  remaining to walk: {len(todo_pids)}")
    if done_pids:
        print(f"done id range:   {done_pids[0]}..{done_pids[-1]}")
    if todo_pids:
        print(f"todo id range:   {todo_pids[0]}..{todo_pids[-1]}\n")

    sample = (
        [("done", p) for p in _spread(done_pids, N_DONE_SAMPLES)]
        + [("todo", p) for p in _spread(todo_pids, N_TODO_SAMPLES)]
    )
    kept = 0
    rows: list[str] = []
    for band, pid in sample:
        earliest_ts, latest_ts = cdx[pid]
        mark = len(_CAP.msgs)
        try:
            art = ing._fetch_and_build(pid, earliest_ts, latest_ts, START, END)
        except Exception as exc:  # _WaybackBanned or fail-loud 5xx
            rows.append(f"  [{band}] pub/{pid}: RAISED {type(exc).__name__}: {exc}")
            break
        # Reason = the log lines this call emitted that name this pid.
        why = "; ".join(m for m in _CAP.msgs[mark:] if f"pub/{pid}" in m) or "(no log)"
        if art is not None:
            kept += 1
            rows.append(
                f"  [{band}] pub/{pid}: KEPT  date={art.published_at[:10]}  "
                f"words={len(art.body.split())}  title={art.title[:50]!r}"
            )
        else:
            rows.append(f"  [{band}] pub/{pid}: dropped — {why}")

    print("\n===== PROBE RESULTS =====")
    for r in rows:
        print(r)
    print(f"\nkept {kept}/{len(sample)} sampled "
          f"({len([s for s in sample if s[0] == 'todo'])} from the remaining band)")
    print(
        "\nINTERPRETATION:\n"
        "  - todo-band KEPTs with real dates  -> extraction works, RESUME is safe.\n"
        "  - done-band all dropped with pre-2010 page_date -> the 5879 drops are\n"
        "    legitimate out-of-window content, not a bug.\n"
        "  - todo-band all dropped as interstitial / no-date -> extraction is\n"
        "    BROKEN; do NOT resume — fix _fetch_and_build first.\n"
    )


if __name__ == "__main__":
    main()
