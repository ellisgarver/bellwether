#!/bin/bash
# SLURM job script: BERTopic stability evaluation on UChicago RCC (Midway3).
#
# Refits BERTopic 20 times (config.validation.bootstrap_replicates) on the
# full corpus and reports mean/std NMI + ARI vs. the baseline fit. CPU-only —
# same resource profile as cluster_rcc.sh but longer wall time.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake
#   CPUs:      8
#   RAM:       32 GB
#   Time:      4 h  (≈ 20 × 8 min per replicate, with margin)
#
# Submit:
#   sbatch scripts/rcc/stability_rcc.sh
#
# Output:
#   logs/stability_rcc_<jobid>.log  (stdout only — no parquet artifacts)

#SBATCH --job-name=mnd-stability
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/stability_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
# ADR-063 persistence: data on backed-up /home (never scratch/purge); HF cache stays on scratch
export MND_DATA_ROOT="/home/ehgarver/bellwether-data"
cd "$REPO_ROOT"

mkdir -p logs

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

python scripts/run_pipeline.py stability

echo "Stability complete: $(date)"
