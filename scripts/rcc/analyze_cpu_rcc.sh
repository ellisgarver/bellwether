#!/bin/bash
# SLURM job script: downstream analysis -> dashboard artifacts on RCC (Midway3),
# CPU-only variant of analyze_rcc.sh.
#
# Why a CPU variant: the analyze step's only GPU use is embedding the ~20 JEL
# prototype descriptions + per-cluster representation strings (a few hundred short
# texts) for nearest-prototype scope assignment. The dominant cost -- PyMC NUTS
# sampling for every in-scope cluster -- runs on CPU regardless. Loading
# Qwen3-Embedding-8B on CPU for a few hundred short encodes is bounded (~tens of
# minutes), so the whole step runs on the caslake CPU partition and skips the
# a100 queue entirely (which has repeatedly cost 24h+ of wait). R0/curve outputs
# are identical to the GPU path -- only the JEL embed device differs.
#
# Use this for re-analyses that change the analysis layer (staging, priors,
# naming) but not the embeddings/clustering. For a run that must re-fit dynamics
# (e.g. a prior change), the fit cache under data/processed/dashboard/.fit_cache
# is invalidated automatically when config.dynamics changes; delete it to force a
# clean re-fit.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake (CPU)
#   CPUs:      8   (PyMC chains)
#   RAM:       64 GB   (8B model on CPU in fp16 ~16 GB + headroom)
#   Time:      18 h   (full dynamics re-fit is the pole; JEL embed is minutes)
#
# Chain manually, or submit standalone after cluster has produced clusters.parquet
# + embeddings.npy:
#   sbatch scripts/rcc/analyze_cpu_rcc.sh

#SBATCH --job-name=mnd-analyze-cpu
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=18:00:00
#SBATCH --output=logs/analyze_cpu_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"
mkdir -p logs data/processed/dashboard

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
# Keep BLAS from oversubscribing across the PyMC chain processes.
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2

echo "===== mnd-analyze-cpu ====="
echo "Job ID:   $SLURM_JOB_ID"
echo "Node:     $(hostname)"
echo "CPUs:     ${SLURM_CPUS_PER_TASK:-?}"
echo "Started:  $(date)"
echo "==========================="

python scripts/run_pipeline.py analyze

echo "===== Complete: $(date) ====="
INDEX="data/processed/dashboard/index.json"
if [[ -f "$INDEX" ]]; then
    ls -lh "$INDEX"
    python -c "import json; d=json.load(open('$INDEX')); print(f'Narratives: {d[\"n_narratives\"]}')"
else
    echo "ERROR: expected dashboard index not found at $INDEX" >&2
    exit 1
fi
