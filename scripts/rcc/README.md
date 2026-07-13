# RCC scripts

The scripts here cover two distinct phases:

- **Full rebuild** (`submit_parallel_ingest.sh` → individual `*_rcc.sh` jobs) — the one-time
  historical ingest and base-model build run as a parallel SLURM fan-out. Done once; not
  repeated unless the corpus window or embedding model changes.
- **Weekly update** (`update_rcc.sh`) — a self-resubmitting SLURM job that runs each week
  unattended: delta ingest → merge → analyze → name → push artifacts → deploy.

## Weekly chain

### Enroll

```bash
# on RCC, from the repo root
git pull origin main                          # pull latest code before enrolling
sbatch --begin=2026-07-18T06:00 scripts/rcc/update_rcc.sh
```

The job queues its own successor (`sbatch --begin=now+7days`) as its first action, so a
single `sbatch` starts the chain. Anchor to a specific datetime to fix the cadence day and
hour.

Validate without enrolling (runs once, no successor):

```bash
MND_NO_RESUBMIT=1 sbatch scripts/rcc/update_rcc.sh
```

### Inspect / stop / re-enroll

```bash
squeue -u $USER -n mnd-update          # see the pending successor
scancel -n mnd-update                  # stop the chain
sbatch --begin=<datetime> scripts/rcc/update_rcc.sh   # re-enroll
```

The job mails on END and FAIL. A Monday with no email means the successor vanished
(maintenance window cancellation) — re-enroll.

### What the first weekly bake will materialize

Three features land with the next successful `analyze` run; the front end already renders
them, but the artifacts are absent until then:

1. **Sub-floor heating cards** — clusters below the charting floor whose corpus volume is
   heating will appear as "not yet charted" cards on the emerging page.
2. **Staleness override stages** — narratives last active more than 16 weeks behind the
   corpus frontier are forced dormant regardless of trend (fixes e.g. clusters with no
   activity since 2013 showing as growth).
3. **Full-corpus composition charts** — the source and JEL breakdowns on the data page
   will switch from the charted-narratives subset to the complete corpus. Until then, the
   charts show the charted subset with a "charted narratives" label.

## Prerequisites (one-time, already done)

- `data/` symlinked to `/home/ehgarver/bellwether-data` — run `scripts/rcc/link_data_home.sh`
  if the symlink is missing (e.g. after a scratch purge).
- Base model at `data/processed/topic_model/` (written by the full rebuild).
- Git push credentials for origin on the RCC checkout.
- `.env` at the repo root with `GOVINFO_API_KEY` and `MEDIACLOUD_API_KEY`; backup at
  `/home/ehgarver/bellwether-data/.env.backup`.

## REPO_ROOT note

All RCC scripts hardcode `REPO_ROOT=/scratch/midway3/ehgarver/macro-narrative-dynamics`.
This is intentional — sbatch spools scripts before running them, so `$BASH_SOURCE` cannot
resolve the repo at runtime.

To rename the scratch directory (not before the naming job and first weekly cycle complete):

1. `scancel -n mnd-update` — park the self-resubmitting chain.
2. On RCC: `mv /scratch/midway3/ehgarver/macro-narrative-dynamics /scratch/midway3/ehgarver/bellwether`
   and re-run `scripts/rcc/link_data_home.sh` (re-creates the `data/` symlink).
3. One commit: update the 13 `REPO_ROOT=` lines in this directory and the `REMOTE_REPO=`
   line in `scripts/publish.sh`; on RCC `git remote set-url origin https://github.com/ellisgarver/bellwether.git`.
4. Re-enroll: `sbatch --begin=<next Saturday 00:00> scripts/rcc/update_rcc.sh`.
5. Locally and on RCC: `pip install -e . --no-deps` so the editable-install metadata picks
   up the `pyproject.toml` rename (import path `mnd` is unchanged; nothing breaks until then,
   metadata is just stale).
