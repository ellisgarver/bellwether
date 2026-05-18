#!/bin/bash
# SLURM job script: institutional+academic corpus ingestion on UChicago RCC (Midway3).
#
# Covers Tiers 1–2 (ADR-010 / MND_PROJECT_SPEC.md):
#   Tier 1 — Federal Reserve (FOMC, speeches, Beige Book, FEDS Notes, MPR),
#             Regional Feds (NY, SF, Chicago, Atlanta, Dallas, StLouis, Cleveland),
#             IMF (Blog/WEO/GFSR/WPs), BIS (QR/WPs), CEA, CBO, Treasury/OFR,
#             Congressional testimony (Treasury Sec)
#             NOTE: Jackson Hole removed (ADR-012) — covered by Fed speeches ingestor
#   Tier 2 — VoxEU, Brookings, PIIE, CFR
#             (arXiv removed ADR-012; NBER/SSRN excluded from historical — Phase 6 only)
#
# JOURNALISM TIER REMOVED (ADR-010): AP News, Reuters, MarketWatch are no longer
# in the semantic corpus. Do not add them back without a new ADR.
#
# All via direct fetch / institutional RSS — sequential, network I/O bound.
# No GPU or large RAM needed.
#
# Checkpoint/resume: if the job times out, re-submitting resumes automatically.
# Completed sub-sources are recorded in .institutional_checkpoint.json and
# skipped on restart.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      4  (sequential RSS/HTTP fetches; extra cores unused)
#   RAM:       8 GB
#   Time:      36 h  (full fresh 2010-2026 run: VoxEU ~6.5h + Brookings ~6.25h +
#                     Congressional ~1.5h + IMF Coveo 16y ~3h + CBO sitemap ~1h +
#                     CFR sitemap ~30min + Fed/FedRegional/BIS/Treasury/PIIE ~3h)
#
# Canonical entry point is scripts/rcc/submit_full_pipeline.sh, which chains:
#   ingest → filter-pre-embed → filter → embed (primary) → cluster
# This script is the first link in that chain; submit it standalone only for
# ingest-only runs (e.g. to populate raw JSONL without re-embedding).
#
# Custom date range (standalone):
#   sbatch --export=START=2010-01-01,END=2024-12-31 \
#       scripts/rcc/ingest_institutional_rcc.sh
#
# IMF coverage: requires curl_cffi==0.15.0 in the mnd conda env (ADR-014).
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-ingest-inst
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=36:00:00
#SBATCH --output=logs/ingest_institutional_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/raw/articles

MND_CONDA_ENV="/home/ehgarver/.conda/envs/mnd"
export PATH="${MND_CONDA_ENV}/bin:$PATH"
export PYTHONNOUSERSITE=1
# Verify we are using the right Python before any work starts
PYTHON_USED="$(which python)"
if [[ "$PYTHON_USED" != "${MND_CONDA_ENV}/bin/python" ]]; then
    echo "ERROR: expected ${MND_CONDA_ENV}/bin/python but got $PYTHON_USED" >&2
    exit 1
fi
echo "Python: $PYTHON_USED"

export USE_TF=0
export KERAS_BACKEND=torch

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"

echo "===== mnd-ingest-inst ====="
echo "Job ID:  $SLURM_JOB_ID"
echo "Node:    $(hostname)"
echo "Window:  $START → $END"
echo "Sources: institutional (Tiers 1–2; ADR-010)"
echo "Started: $(date)"
echo "==========================="

python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources institutional

echo "===== Complete: $(date) ====="
INST_JSONL="data/raw/articles/institutional_${START}_${END}.jsonl"
if [[ -f "$INST_JSONL" ]]; then
    COUNT=$(wc -l < "$INST_JSONL")
    SIZE=$(du -sh "$INST_JSONL" | cut -f1)
    echo "Output: $INST_JSONL ($COUNT articles, $SIZE)"
else
    echo "ERROR: expected output not found at $INST_JSONL" >&2
    exit 1
fi
