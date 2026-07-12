# Pending removals — do NOT delete until final sign-off

Prepared 2026-07-11. Everything here stays in place until the re-pipeline is
fully done and the site is live; then remove in one reviewed commit per group.

## 1. Certain — remove at launch cleanup

- `data/naming_cache/name_*.json` (366 tracked pre-v3 files + all files
  written by the killed 2026-07-12 v3 run, job 51882669) —
  `display.naming.prompt_version` went 2 → 3 (2026-07-11) → 4 (2026-07-12,
  with the model switch to qwen2.5:7b), so every earlier signature is a dead
  key. After the mnd-name job regenerates the cache under v4: `git rm` /
  delete the old files. Simple rule: any `name_*.json` not rewritten by the
  final v4 run is stale.
- `.claude/settings.local.json` (untracked) — local Claude Code permissions;
  delete when the project wraps. Never publish.
- Claude auto-memory dir
  `~/.claude/projects/-Users-ellisgarver-Projects-bellwether/memory/` —
  outside the repo; delete when the project no longer needs session memory.
- Scratch/one-off local files: `web/.DS_Store`, `web/src/.DS_Store`
  (untracked, ignored) — `find . -name .DS_Store -delete` anytime.

## 2. After the GitHub Action deploy is proven (first weekly cycle green)

- `scripts/publish.sh` **full mode** (already guarded behind `FORCE_FULL=1`,
  2026-07-11) — delete the full-mode branch outright, keep `--site-only` as the
  manual fallback. Reason: production deploys are RCC → `site-data` branch →
  Action; full mode commits `data/naming_cache` to main, which can wedge the
  RCC checkout through the `data/` → /home symlink.

## 3. Coordinated RCC rename (one commit + one RCC session; NOT before the
##    naming job and first weekly cycle complete)

The repo directory on RCC scratch is still `/scratch/midway3/ehgarver/`
`macro-narrative-dynamics`; 13 files hardcode it (all `scripts/rcc/*.sh`
`REPO_ROOT=` lines + `scripts/publish.sh` `REMOTE_REPO`). Hardcoding is
deliberate (sbatch spools scripts, so `$BASH_SOURCE` can't find the repo).
To retire the old name everywhere:
1. `scancel -n mnd-update` (park the self-resubmitting chain).
2. On RCC: `mv /scratch/midway3/ehgarver/macro-narrative-dynamics /scratch/midway3/ehgarver/bellwether`
   and re-run `scripts/rcc/link_data_home.sh` (re-create the `data/` symlink).
3. One commit: `sed` the 13 `REPO_ROOT`/`REMOTE_REPO` lines to the new path;
   `git remote set-url origin https://github.com/ellisgarver/bellwether.git` on RCC.
4. Re-enroll: `sbatch --begin=<next Monday 06:00> scripts/rcc/update_rcc.sh`.
Also then: `pip install -e . --no-deps` on RCC + locally so the editable-install
metadata picks up the `pyproject.toml` rename to `bellwether` (import path `mnd`
is unchanged; nothing breaks until then, metadata is just stale).

## 4. Review before removing (working diagnostics — may stay)

- `scripts/rcc/integration_test_rcc.sh` — full-chain smoke test; superseded by
  the validated weekly chain? Keep if still used for post-change validation.
- `scripts/rcc/stability_rcc.sh` — bootstrap-NMI diagnostic (reported, not
  gated). Referenced by METHODOLOGY principle 3; keep unless the diagnostic is
  retired by an ADR.
- `scripts/verify_coverage.py` — pre-launch coverage QA (used 2026-07-10);
  useful for future re-ingests. Keep.
- `data/anchors/fizzled_counterparts_seed.jsonl` — DRAFT seeds guarded by
  `test_fizzled_seed_marked_as_draft`; remove test + file together if the
  fizzled-counterparts idea is formally dropped, otherwise keep.

## 5. Explicitly KEEP (checked, not stale)

- `tests/test_scaffold.py` — config-invariant guards, all still asserted
  against the live config (docstrings refreshed 2026-07-11).
- All 12 `scripts/rcc/*.sh` build scripts — the tested full-rebuild fan-out.
- `docs/architecture_decisions.md` — append-only decision log (condensed for
  publication 2026-07-11, entries preserved).
