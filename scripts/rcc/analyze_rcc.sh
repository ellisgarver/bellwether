#!/bin/bash
# SLURM job script: downstream analysis → dashboard artifacts on RCC (Midway3).
#
# The pipeline→front-end seam (ADR-043). Recomputes the entire analysis layer
# from the persisted clustering — corpus-base-rate normalization (ADR-045), JEL
# scope (ADR-020), four-lens Bayesian dynamics (ADR-039), stage classification
# (ADR-019), similar narratives + UMAP map (ADR-044) — and bakes the artifact
# JSON the static Astro site reads. No re-embedding: reads clusters.parquet +
# embeddings.npy only.
#
# Hybrid resource profile:
#   - GPU (A100): loads Qwen3-Embedding-8B briefly to embed the ~20 JEL prototype
#     descriptions + per-cluster term lists for nearest-prototype scope assignment.
#   - CPU: PyMC NUTS sampling for every in-scope cluster (4 chains) — the long pole.
# One A100 job covers both; PyMC runs on the node's CPUs while the GPU sits idle
# after the JEL pass.
#
# Resource spec:
#   Account:   pi-dachxiu
#   GPU:       1x A100 40GB (constraint=a100) — same as embed (8B needs >16 GB)
#   CPUs:      8   (PyMC chains)
#   RAM:       64 GB
#   Time:      12 h   (JEL embed ~minutes; PyMC scales with in-scope cluster count)
#
# Canonical chain (use scripts/rcc/submit_parallel_ingest.sh):
#   ingest → filter-pre-embed → filter → embed (primary) → cluster → analyze
#
# Or chain manually after cluster:
#   CLUSTER_JID=$(sbatch --parsable scripts/rcc/cluster_rcc.sh)
#   sbatch --dependency=afterok:$CLUSTER_JID scripts/rcc/analyze_rcc.sh
#
# Output:
#   data/processed/dashboard/index.json + narrative_<id>.json
#   logs/analyze_rcc_<jobid>.log
#
# All output in /scratch/midway3/ehgarver/ — never in PI project folder.

#SBATCH --job-name=mnd-analyze
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --constraint=a100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/analyze_rcc_%j.log
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
export MND_EMBEDDING_DEVICE=cuda
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "===== mnd-analyze ====="
echo "Job ID:   $SLURM_JOB_ID"
echo "Node:     $(hostname)"
echo "GPU:      $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
echo "Started:  $(date)"
echo "======================="

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
