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
#   GPU:       1x A100 40GB (llama3.1 8B fits in a fraction of it; the GPU
#              buys ~10x tokens/s over CPU for the one-time directory backfill)
#   CPUs:      8
#   RAM:       32 GB
#   Time:      12 h  (full post-rebuild backfill ~2-4 h on A100; warm-cache
#              re-runs are minutes)
#
# Chain after analyze, or submit standalone against existing artifacts:
#   sbatch --dependency=afterok:<analyze_jobid> scripts/rcc/name_rcc.sh

#SBATCH --job-name=mnd-name
#SBATCH --account=pi-dachxiu
#SBATCH --partition=gpu
#SBATCH --constraint=a100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=logs/name_rcc_%j.log
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

# User-space Ollama on scratch (no root, no home-quota pressure). The tarball
# unpacks bin/ollama + lib/ollama; models are pulled once and reused.
OLLAMA_ROOT="/scratch/midway3/ehgarver/ollama"
export OLLAMA_MODELS="$OLLAMA_ROOT/models"
export OLLAMA_HOST="127.0.0.1:11434"
mkdir -p "$OLLAMA_ROOT" "$OLLAMA_MODELS"
if [[ ! -x "$OLLAMA_ROOT/bin/ollama" ]]; then
    echo "Installing Ollama to $OLLAMA_ROOT"
    curl -fsSL https://ollama.com/download/ollama-linux-amd64.tgz | tar -xz -C "$OLLAMA_ROOT"
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

MODEL="${MND_NAMING_MODEL:-llama3.1}"
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
