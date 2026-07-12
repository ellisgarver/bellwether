#!/bin/bash
# SLURM job script: display-name resolution on RCC (Midway3) — ADR-073.
#
# Serves a user-space Ollama from scratch storage and runs the `name` command
# against the baked dashboard artifacts, patching titles in place: full
# title + description for surfaced narratives, terms-grounded titles for every
# non-surfaced directory entry. Same open model, endpoint scheme, and committed
# cache as the local path (ADR-067/070) — only the execution host differs.
#
# Naming is cache-incremental (one file per cluster under data/naming_cache),
# so a timeout or requeue resumes where it stopped; re-runs are no-ops for
# unchanged clusters. The first run after a full re-cluster is the expensive
# one (~7k titles); the A100 finishes it in a few hours. If the a100 queue is
# backed up, the job also completes on a CPU partition — Ollama falls back to
# CPU inference, slower but resumable.
#
# Resource spec:
#   Account:   pi-dachxiu
#   GPU:       1 GPU, any node type — the pinned Ollama's CUDA 12 backend
#              covers v100/rtx6000/a100 on the cluster's 535 driver. Pinning
#              a100 alone queues for days behind fairshare (one a100 node in
#              the partition). Midway3's submit filter rejects OR constraints
#              ("rtx6000|a100") and empty ones (""); pass a single concrete
#              feature on the sbatch line to target an idle node type, e.g.
#              sbatch --constraint=v100 scripts/rcc/name_rcc.sh
#   CPUs:      8
#   RAM:       32 GB
#   Time:      6 h  (full post-rebuild backfill ~2-4 h on A100, more on the
#              smaller cards; naming is cache-incremental, so a timeout
#              resumes on resubmit and warm-cache re-runs are minutes)
#
# Chain after analyze, or submit standalone against existing artifacts:
#   sbatch --dependency=afterok:<analyze_jobid> scripts/rcc/name_rcc.sh

#SBATCH --job-name=mnd-name
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=6:00:00
#SBATCH --output=logs/name_rcc_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ehgarver@uchicago.edu

set -euo pipefail

REPO_ROOT="/scratch/midway3/ehgarver/macro-narrative-dynamics"
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

# User-space Ollama on scratch (no root, no home-quota pressure). The tarball
# unpacks bin/ollama + lib/ollama; models are pulled once and reused.
# PINNED to v0.13.2: Midway3 GPU nodes run NVIDIA driver 535, and newer
# Ollama builds are CUDA-13-only (driver >= 550), so they refuse every GPU
# in the partition and silently fall back to ~4 tok/s CPU inference (jobs
# 51872345/51874699). v0.13.2 is the last-tested dual cuda_v12/cuda_v13
# release; it selects CUDA 12 on driver 535 and runs on any gpu node.
# Do not bump this pin until the cluster driver reaches 550+.
OLLAMA_VERSION="v0.13.2"
OLLAMA_ROOT="/scratch/midway3/ehgarver/ollama"
export OLLAMA_MODELS="$OLLAMA_ROOT/models"
export OLLAMA_HOST="127.0.0.1:11434"
mkdir -p "$OLLAMA_ROOT" "$OLLAMA_MODELS"
if [[ ! -x "$OLLAMA_ROOT/bin/ollama" ]]; then
    echo "Installing Ollama $OLLAMA_VERSION to $OLLAMA_ROOT"
    curl -fsSL "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tgz" \
        | tar -xz -C "$OLLAMA_ROOT"
fi
export PATH="$OLLAMA_ROOT/bin:$PATH"

ollama serve >> "logs/ollama_serve_${SLURM_JOB_ID}.log" 2>&1 &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
    curl -sf "http://${OLLAMA_HOST}/api/tags" > /dev/null && break
    sleep 2
done
curl -sf "http://${OLLAMA_HOST}/api/tags" > /dev/null || {
    echo "ERROR: Ollama did not come up (see logs/ollama_serve_${SLURM_JOB_ID}.log)" >&2
    exit 1
}

MODEL="${MND_NAMING_MODEL:-qwen2.5:7b}"
ollama pull "$MODEL"

echo "===== mnd-name ====="
echo "Job ID:   $SLURM_JOB_ID"
echo "Node:     $(hostname)"
echo "GPU:      $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 || echo none)"
echo "Model:    $MODEL"
echo "Started:  $(date)"
echo "===================="

python scripts/run_pipeline.py name

echo "===== Complete: $(date) ====="
python -c "import json; cl=json.load(open('data/processed/dashboard/clusters_all.json'))['clusters']; print(f'Directory: {sum(1 for c in cl if c.get(\"label_human\"))}/{len(cl)} clusters carry display names')"
