#!/bin/bash
# SLURM job script: full-corpus embedding on UChicago RCC (Midway3).
#
# Targets one A100 GPU. Embedding Qwen3-0.6B at max_seq_len=32768 on CUDA
# requires ~4 GB VRAM for the model + ~2 GB per batch; a single A100 (40 GB)
# handles this with room to spare. Adjust --partition and --account below.
#
# Submit from the repo root on Midway3:
#   sbatch scripts/rcc/embed_rcc.sh
#
# Prerequisites:
#   1. Scratch path exists: /scratch/midway3/ehgarver
#   2. `conda activate mnd` works (see setup notes below)
#   3. Processed articles parquet at data/processed/articles.parquet (run filter first)
#
# Output: data/processed/embeddings.npy + logs/embed_rcc_<jobid>.log
#
# Conda setup (run once interactively on Midway3):
#   module load python/anaconda-2023.09
#   conda create -n mnd python=3.12 -y
#   conda activate mnd
#   pip install -r requirements.txt
#   pip install torch --index-url https://download.pytorch.org/whl/cu121

#SBATCH --job-name=mnd-embed
#SBATCH --account=pi-ehgarver          # your own allocation; adjust if under PI account
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00                # 4 h; full 2010-present corpus ~2-3 h estimated
#SBATCH --output=logs/embed_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="$HOME/Projects/macro-narrative-dynamics"
cd "$REPO_ROOT"

module load python/anaconda-2023.09
conda activate mnd

# Prevent TF import stall (see ADR-006); use full max_seq_len on CUDA
export USE_TF=0
export KERAS_BACKEND=torch
export MND_EMBEDDING_DEVICE=cuda
# MND_MAX_SEQ_LEN intentionally NOT set → uses config.yaml default (32768)

echo "Job $SLURM_JOB_ID started: $(date)"
echo "Running on $(hostname), GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"

python scripts/run_pipeline.py embed --role primary

echo "Embedding complete: $(date)"
echo "Output: $REPO_ROOT/data/processed/embeddings.npy"
ls -lh data/processed/embeddings.npy
