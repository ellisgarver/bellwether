#!/bin/bash
# SLURM job script: full-corpus BERTopic clustering on UChicago RCC (Midway3).
#
# BERTopic/HDBSCAN is CPU-bound after UMAP reduction. No GPU required.
#
# Resource spec (confirmed 2026-05-04):
#   Account:   pi-dachxiu
#   Partition: caslake (standard compute — 32 GB fits comfortably)
#   CPUs:      8
#   RAM:       32 GB
#   Time:      8 h
#
# Submit after embed completes:
#   sbatch scripts/rcc/cluster_rcc.sh
#
# Or chain as a dependency (preferred):
#   EMBED_JID=$(sbatch --parsable scripts/rcc/embed_rcc.sh)
#   sbatch --dependency=afterok:$EMBED_JID scripts/rcc/cluster_rcc.sh
#
# Runs three granularity levels (fine/medium/coarse) per config.yaml and
# 20 bootstrap replicates. All UMAP/HDBSCAN parameters are pre-specified in
# config.yaml — do not tune at this stage.
#
# Output:
#   data/processed/clusters.parquet
#   data/processed/topic_info.parquet
#   logs/cluster_rcc_<jobid>.log
#
# All data output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-cluster
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=logs/cluster_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/processed

MND_CONDA_ENV="/home/ehgarver/.conda/envs/mnd"
export PATH="${MND_CONDA_ENV}/bin:$PATH"
export PYTHONNOUSERSITE=1
PYTHON_USED="$(which python)"
if [[ "$PYTHON_USED" != "${MND_CONDA_ENV}/bin/python" ]]; then
    echo "ERROR: expected ${MND_CONDA_ENV}/bin/python but got $PYTHON_USED" >&2
    exit 1
fi
echo "Python: $PYTHON_USED"

export USE_TF=0
export KERAS_BACKEND=torch
export MND_EMBEDDING_DEVICE=cpu

echo "Job $SLURM_JOB_ID started: $(date)"
echo "Running on $(hostname), CPUs: $SLURM_CPUS_PER_TASK, RAM: ${SLURM_MEM_PER_NODE:-32768} MB"

python scripts/run_pipeline.py cluster

echo "Clustering complete: $(date)"
ls -lh data/processed/clusters.parquet data/processed/topic_info.parquet 2>/dev/null || \
    echo "WARNING: expected output files not found — check log above"
