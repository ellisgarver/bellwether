#!/bin/bash
# SLURM job: re-ingest only the sub-ingestors whose fixes landed on
# 2026-05-18 (FederalReserveIngestor for Beige Book + FEDS Notes,
# FedRegionalIngestor for fed_chicago date inference, VoxEUIngestor for
# date-range sharding, CBOIngestor for curl_cffi swap).
#
# Strategy: mark those four sub-ingestors as `failed` in the checkpoint
# JSON, leave everything else as `completed`, then run the standard
# institutional ingest. The InstitutionalIngestor.fetch() loop will skip
# all completed sources and re-run only the failed ones, appending new
# records to data/raw/articles/institutional_*.jsonl.
#
# Duplicates from sub-ingestors that re-emit already-captured articles
# (e.g. FederalReserveIngestor re-emitting FOMC statements) are handled
# by the filter/dedup stage on a fresh `filter` pass after this completes.
#
# After this job finishes, re-run:
#   sbatch scripts/rcc/filter_pre_embed_rcc.sh   # then dedup -> filter -> embed -> cluster
# Or use the full chain in submit_full_pipeline.sh with NUKE_RAW=0.

#SBATCH --job-name=mnd-patch-ingest
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=08:00:00
#SBATCH --output=logs/patch_ingest_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/raw/articles

MND_CONDA_ENV="/home/ehgarver/.conda/envs/mnd"
export PATH="${MND_CONDA_ENV}/bin:$PATH"
export PYTHONNOUSERSITE=1
PYTHON_USED="$(which python)"
if [[ "$PYTHON_USED" != "${MND_CONDA_ENV}/bin/python" ]]; then
    echo "ERROR: expected ${MND_CONDA_ENV}/bin/python but got $PYTHON_USED" >&2
    exit 1
fi
echo "Python: $PYTHON_USED"

CKPT="data/raw/articles/.institutional_checkpoint.json"
if [[ ! -f "$CKPT" ]]; then
    echo "ERROR: expected checkpoint $CKPT not found." >&2
    exit 1
fi

# Reset the four targeted sub-ingestors to `failed` so the loop re-runs them.
# Untouched sub-ingestors (imf, congressional, brookings, etc.) stay completed.
python - <<'PY'
import json, pathlib
ckpt = pathlib.Path("data/raw/articles/.institutional_checkpoint.json")
data = json.loads(ckpt.read_text())
targets = ["federalreserve", "fed_regional", "voxeu", "cbo"]
for sid in targets:
    prior = data.get(sid, {})
    data[sid] = {"status": "failed", "error": f"reset for patch re-ingest (was: {prior})"}
ckpt.write_text(json.dumps(data, indent=2))
print(f"Reset {len(targets)} sub-ingestors: {targets}")
PY

echo "Job $SLURM_JOB_ID started: $(date)"
echo "Running on $(hostname)"

# Use the same start/end window as the original full run.
python scripts/run_pipeline.py ingest \
    --sources institutional \
    --start 2010-01-01 \
    --end "$(date +%F)"

echo "Patch ingest complete: $(date)"
echo "--- Final checkpoint ---"
cat "$CKPT"
