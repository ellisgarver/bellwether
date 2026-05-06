#!/bin/bash
# SLURM job script: full-corpus historical ingestion on UChicago RCC (Midway3).
#
# Phase 2 semantic corpus (ADR-008, ADR-009):
#   --sources institutional   Fed, IMF, BIS, CEA, CBO, Treasury/OFR, NBER,
#                             SSRN, VoxEU, Brookings, PIIE (RSS + direct fetch)
#   --sources apnews          AP News via Wayback CDX (2010-present)
#   --sources marketwatch     MarketWatch via Wayback CDX (2010-present;
#                             consistent coverage from 2015)
#
# Network I/O bound — no GPU or large RAM needed. Runtime depends on Wayback
# CDX response latency. AP News + MarketWatch use 8 parallel fetch workers;
# institutional is sequential (RSS-bound). Estimate 36-48 h for a full
# 2010-present historical run. Checkpoint/resume: re-submitting the same job
# after a timeout will skip already-fetched URLs and append to existing JSONL.
#
# Resource spec (confirmed 2026-05-04):
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      8 (8 parallel Wayback fetch workers for AP News and MarketWatch)
#   RAM:       16 GB
#   Time:      48 h
#
# Submit from Midway3:
#   sbatch scripts/rcc/ingest_rcc.sh
#
# Custom date range:
#   sbatch --export=START=2010-01-01,END=2024-12-31 scripts/rcc/ingest_rcc.sh
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-ingest
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=48:00:00
#SBATCH --output=logs/ingest_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/raw/articles

module load python/anaconda-2023.09
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch

START="${START:-2010-01-01}"
END="${END:-$(date +%Y-%m-%d)}"

echo "Job $SLURM_JOB_ID started: $(date)"
echo "Ingestion window: $START → $END"
echo "Running on $(hostname)"

# Tier 1-3: institutional policy, academic analytical, policy-journalism bridge
python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources institutional

# Tier 4: AP News wire journalism (Wayback CDX)
python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources apnews

# Tier 4: MarketWatch analytical journalism (Wayback CDX; consistent from 2015)
python scripts/run_pipeline.py ingest \
    --start "$START" \
    --end "$END" \
    --sources marketwatch

echo "Ingestion complete: $(date)"
echo "Raw article files:"
ls -lh data/raw/articles/*.jsonl 2>/dev/null | tail -20 || echo "(no JSONL files found)"
echo "Total files: $(ls data/raw/articles/*.jsonl 2>/dev/null | wc -l)"
