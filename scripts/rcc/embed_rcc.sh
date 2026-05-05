#!/bin/bash
# SLURM job script: full-corpus embedding on UChicago RCC (Midway3).
#
# Targets one V100 GPU (preferred; falls back to any available GPU if V100
# queue is long — remove the constraint line to allow any GPU type).
#
# Resource spec (confirmed 2026-05-04):
#   Account:   pi-dachxiu
#   GPU:       1x V100 (constraint=v100)
#   CPUs:      8
#   RAM:       16 GB
#   Time:      12 h (conservative; full corpus ~3-5 h estimated on V100)
#   Cost:      ~300 SUs worst case (allocation balance: 1,532,273 SUs)
#
# Role selection:
#   Default (ROLE=primary):    Qwen3-Embedding-0.6B — production embeddings
#                              for BERTopic clustering and dynamics fitting
#   Override (ROLE=comparator): all-mpnet-base-v2 — Phase 3 look-ahead
#                              sensitivity check (pre vs post 2021 sub-periods)
#
#   Submit production run:
#     sbatch scripts/rcc/embed_rcc.sh
#
#   Submit comparator (look-ahead check):
#     sbatch --export=ROLE=comparator scripts/rcc/embed_rcc.sh
#
# Prerequisites (run on Midway3 interactively once):
#   git clone https://github.com/ellisgarver/macro-narrative-dynamics.git \
#       /scratch/midway3/ehgarver/macro-narrative-dynamics
#   cd /scratch/midway3/ehgarver/macro-narrative-dynamics
#   module load python/anaconda-2023.09
#   conda create -n mnd python=3.12 -y
#   conda activate mnd
#   pip install -r requirements.txt
#   pip install torch --index-url https://download.pytorch.org/whl/cu121
#
# All data output goes to /scratch/midway3/ehgarver/macro-narrative-dynamics/data/
# Never write to PI project folder.

#SBATCH --job-name=mnd-embed
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --constraint=v100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=logs/embed_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
cd "$REPO_ROOT"

mkdir -p logs data/processed

module load python/anaconda-2023.09
conda activate mnd

export USE_TF=0
export KERAS_BACKEND=torch
export MND_EMBEDDING_DEVICE=cuda
# MND_MAX_SEQ_LEN intentionally NOT set — uses config.yaml default (32768) on CUDA

ROLE="${ROLE:-primary}"
echo "Job $SLURM_JOB_ID started: $(date)"
echo "Embedding role: $ROLE"
echo "Running on $(hostname), GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"

python scripts/run_pipeline.py embed --role "$ROLE"

echo "Embedding complete: $(date)"
if [ "$ROLE" = "primary" ]; then
    ls -lh data/processed/embeddings.npy
else
    ls -lh data/processed/embeddings_comparator.npy 2>/dev/null || \
        ls -lh data/processed/embeddings_*.npy 2>/dev/null || true
fi
