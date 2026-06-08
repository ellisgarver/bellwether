#!/bin/bash
# SLURM job: ingest a SINGLE basis-set source on UChicago RCC (Midway3).
#
# Generic single-source worker for the parallel-ingest fan-out (ADR-020 basis
# set). The full corpus is split into one job per source so no source starves
# behind a long pole (CBO/NBER/Brookings) and each gets its own wall clock.
# Canonical entry point is scripts/rcc/submit_parallel_ingest.sh, which submits
# all 12 of these with per-source --time limits and chains the downstream
# filter -> embed -> cluster stages on afterok of every ingest job.
#
# Required env:
#   SOURCE   one of: federalreserve fed_regional congressional imf bis
#            treasury_ofr cea voxeu brookings piie cbo nber
#   START    window start (default 2010-01-01)
#   END      window end   (default today)
#
# Resource defaults below are overridden per-source on the sbatch command line
# by the submit script (--job-name, --time). Each source writes its own raw
# JSONL: data/raw/articles/{SOURCE}_{START}_{END}.jsonl — filter-pre-embed
# globs every source file together, so per-source output composes cleanly.
#
# Single-source runs do NOT use the composite .institutional_checkpoint.json:
# re-running a source overwrites its own JSONL from scratch (mode "w"), so the
# stale-checkpoint pitfall (see submit_parallel_ingest.sh) does not apply here.
#
# IMF requires curl_cffi==0.15.0 in the mnd conda env (ADR-014).
# All data output under /scratch/midway3/ehgarver/ — never PI project storage.

#SBATCH --job-name=mnd-ingest-src
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=12:00:00
#SBATCH --output=logs/ingest_%x_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

: "${SOURCE:?Set SOURCE=<source_id> (e.g. SOURCE=brookings)}"

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

export USE_TF=0
export KERAS_BACKEND=torch

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"

echo "===== mnd-ingest source=$SOURCE ====="
echo "Job ID:  ${SLURM_JOB_ID:-<none>}"
echo "Node:    $(hostname)"
echo "Window:  $START → $END"
echo "Python:  $PYTHON_USED"
echo "Started: $(date)"
echo "======================================"

python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources "$SOURCE"

echo "===== Complete: $(date) ====="
OUT_JSONL="data/raw/articles/${SOURCE}_${START}_${END}.jsonl"
if [[ -f "$OUT_JSONL" ]]; then
    COUNT=$(wc -l < "$OUT_JSONL")
    SIZE=$(du -sh "$OUT_JSONL" | cut -f1)
    echo "Output: $OUT_JSONL ($COUNT articles, $SIZE)"
    if [[ "$COUNT" -eq 0 ]]; then
        echo "ERROR: $SOURCE produced 0 articles — under-capture, failing job so the" >&2
        echo "       afterok downstream chain halts and the gap is noticed." >&2
        exit 1
    fi
else
    echo "ERROR: expected output not found at $OUT_JSONL" >&2
    exit 1
fi
