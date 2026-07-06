#!/bin/bash
# SLURM job script: downstream analysis -> dashboard artifacts on RCC (Midway3),
# CPU-only variant of analyze_rcc.sh.
#
# Why a CPU variant: the analyze step needs no GPU at all since ADR-067 — the
# lens fits are deterministic least squares, JEL scope is a cosine over existing
# cluster centroids (the 8B embedder loads only if the fixed JEL prototype
# vectors aren't cached yet), and every stage is cache-incremental (ADR-065).
# Running on the caslake CPU partition skips the a100 queue entirely (which has
# repeatedly cost 24h+ of wait); outputs are identical to the GPU path.
#
# Use this for re-analyses that change the analysis layer (staging, lens config,
# naming) but not the embeddings/clustering. The per-lens fit cache under
# data/processed/dashboard/.fit_cache is invalidated automatically when the
# relevant config changes; delete it to force a clean re-fit.
#
# Resource spec:
#   Account:   pi-dachxiu
#   Partition: caslake (CPU)
#   CPUs:      8
#   RAM:       64 GB   (headroom for a first-time JEL prototype embed on CPU)
#   Time:      4 h    (a warm-cache re-bake is minutes; cold fits well under this)
#
# Chain manually, or submit standalone after cluster has produced clusters.parquet
# + embeddings.npy:
#   sbatch scripts/rcc/analyze_cpu_rcc.sh

#SBATCH --job-name=mnd-analyze-cpu
#SBATCH --account=pi-dachxiu
#SBATCH --partition=caslake
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
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
# Keep the ~16 GB Qwen3-8B HF cache on scratch, not the 30 GB home quota.
export HF_HOME="/scratch/midway3/ehgarver/huggingface"
export HF_HUB_OFFLINE=0
# Keep BLAS threads bounded; the analysis is I/O- and single-core-bound.
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
