# Macro Narrative Dynamics — Claude Code Guide

## Project overview

Quantitative study of narrative lifecycle dynamics in U.S. macro-financial media
discourse. Methodology: embed articles → cluster with BERTopic → fit SIR/logistic
ODE to cluster volume time series → classify lifecycle stage. Full plan and all
architectural decisions are in `docs/handoff_to_claude_code.md` and
`docs/architecture_decisions.md`. Read those before making any structural changes.

## Critical rules (do not violate without an ADR)

- Every threshold and hyperparameter lives in `config/config.yaml`. Never hardcode.
- Every random seed flows from `config.reproducibility.global_random_seed` (42).
- Do not hand-tune any parameter to improve anchor recovery.
- Do not load held-out (2020+) data into clustering or hyperparameter search before Phase 4.
- Do not add closed-source or paid-API dependencies to the core pipeline (ADR-001).
- Paywalled ingestion uses ProQuest TDM Studio only — not Factiva (license prohibits it).
- Any deviation from the above requires a new ADR in `docs/architecture_decisions.md` first.

## Communication style

- For every file created or significantly modified, explain in chat what it does, why it exists, and how it connects to adjacent modules.
- Before every continuation step, summarize what was just completed and what the next step will do — never start a new step silently.
- Never say "shall I continue?" without that context attached.
- Never add Co-Authored-By lines to commit messages.

## Resuming a mid-pilot session

If a session ends while the Phase 1 pilot is running, **do not restart from scratch**.
Check which stages have already written their checkpoint files and resume from the
first missing one.

### Stage → checkpoint file mapping

| Stage | CLI command | Checkpoint file |
|---|---|---|
| ingest (wayback) | `run_pipeline.py ingest --sources wayback,fed --start … --end …` | `data/raw/articles/wayback_*.jsonl` |
| ingest (fed) | _(runs as part of wayback,fed above)_ | `data/raw/articles/fed_*.jsonl` |
| filter | `run_pipeline.py filter` | `data/processed/articles.parquet` |
| embed | `run_pipeline.py embed --role primary` | `data/processed/embeddings.npy` |
| cluster | `run_pipeline.py cluster` | `data/processed/clusters.parquet` |
| stability | `run_pipeline.py stability` | _(stdout only — re-run if unsure)_ |
| validate | `run_pipeline.py validate --anchors …` | _(stdout only — re-run if unsure)_ |

### How to resume

```python
from pathlib import Path

checkpoints = {
    "ingest":    any(Path("data/raw/articles").glob("*.jsonl")),
    "filter":    Path("data/processed/articles.parquet").exists(),
    "embed":     Path("data/processed/embeddings.npy").exists(),
    "cluster":   Path("data/processed/clusters.parquet").exists(),
}
first_missing = next((k for k, done in checkpoints.items() if not done), "stability")
print(f"Resume from: {first_missing}")
```

Or just run `python -c "…"` with the snippet above from the repo root.

Stability and validate write no files — if the session ended during or after
those stages, check the git log for a Phase 1 results commit. If none exists,
re-run them (they are fast relative to embed/cluster).

## Phase status (update this when phases complete)

- [x] Phase 0 — scaffold, configs, anchor set, ingestors, embedding module
- [x] Phase 1 — filtering, dedup, clustering, dynamics, stages, validation, CLI
- [ ] Phase 2 — full ingestion 2010–present (RCC; requires TDM Studio export + PROQUEST_DATASET_ID)
- [ ] Phase 3 — full corpus embedding, look-ahead sensitivity, multi-model dynamics
- [ ] Phase 4 — pre-registration finalized, full anchor + fizzled validation
- [ ] Phase 5 — Streamlit dashboard, Hugging Face Spaces deploy
- [ ] Phase 6 — weekly cron update pipeline
- [ ] Phase 7 — technical report, reproducibility audit

## Running the Phase 1 pilot

```bash
# Install deps first if not done
pip install -r requirements.txt

# Six-month pilot window
python scripts/run_pipeline.py ingest --start 2023-09-01 --end 2024-02-29 --sources wayback,fed
python scripts/run_pipeline.py filter
python scripts/run_pipeline.py embed --role primary
python scripts/run_pipeline.py cluster
python scripts/run_pipeline.py stability
python scripts/run_pipeline.py validate --anchors anchor_01_svb,anchor_07_credit_suisse,anchor_10_soft_landing

# Kill criterion 1: stability exits 0 only if mean NMI ≥ 0.40
# Kill criterion 2: validate exits 0 only if ≥ 7/10 anchors recovered
# If either fails: stop, read the output, do not proceed to Phase 2
```

## Environment

- Local compute: Apple Silicon MPS (MacBook Air M-series) — `embedding_device: auto` detects it
  - Set `MND_MAX_SEQ_LEN=512` in `.env` to avoid OOM on Qwen3-Embedding-0.6B (see ADR-006)
  - `config.yaml` now defaults to 32768; the env var overrides for local runs without touching the file
- Full corpus runs: UChicago RCC (CUDA) — `MND_EMBEDDING_DEVICE=cuda` or set in `.env`; use SLURM scripts in `scripts/rcc/`
- FRED key: add to `.env` when available (not required for pilot — FRED is macro indicators only)
- ProQuest: export a TDM Studio dataset first (see `docs/proquest_tdm_setup.md`), then set `PROQUEST_DATASET_ID` in `.env` before running `--sources paywalled`
- NewsAPI: set `NEWS_API_KEY` in `.env` for Phase 6 live updates (free tier, 100 req/day; not needed for historical ingestion)

## Phase 2 corpus architecture (tight corpus)

**Three-tier corpus (finalized 2026-05-01):**

| Tier | Outlets | Retrieval |
|---|---|---|
| 1 — Core financial press | WSJ, NYT (business), Economist | ProQuest TDM Studio |
| 1 — Core financial press (wire) | Reuters, Bloomberg | Wayback CDX (historical) + NewsAPI (Phase 6 live) |
| 1 — Core financial press | FT | Factiva (TBD — not in TDM Studio dataset) |
| 2 — Adjacent analytical | Bloomberg Opinion, VoxEU, FT Alphaville, Brookings, Peterson, CFR, Axios | Wayback CDX |
| 3 — Institutional | Fed, IMF, BIS, NBER, OECD, CEA, BEA | Direct fetch / fed_site |

**Dropped to supplementary** (coverage gaps → `supplementary_outlets` in whitelist.yaml):
Barron's, MarketWatch, Foreign Affairs, Project Syndicate

**Phase 2 pipeline (run on RCC after ProQuest export ready):**
```bash
# 1. Download ProQuest TDM Studio JSONL → data/raw/articles/
# 2. Full historical ingestion
sbatch scripts/rcc/ingest_rcc.sh          # Wayback + Fed (2010-present)
# (separately copy ProQuest JSONL to data/raw/articles/)

# 3. Filter, QA, embed, cluster
python scripts/run_pipeline.py filter
python scripts/run_pipeline.py corpus-composition --by-tier --output data/processed/corpus_composition.csv
sbatch scripts/rcc/embed_rcc.sh           # or chain with --dependency
sbatch scripts/rcc/cluster_rcc.sh
```

## Key file locations

| What | Where |
|---|---|
| Master config (locked) | `config/config.yaml` |
| Outlet whitelist | `config/whitelist.yaml` |
| Topic filter keywords | `config/topic_filter_keywords.yaml` |
| Anchor narratives (locked) | `data/anchors/anchor_narratives.jsonl` |
| Topic seed articles | `data/anchors/topic_seed_articles.jsonl` |
| Architecture decisions | `docs/architecture_decisions.md` |
| Pre-registration draft | `prereg/PREREGISTRATION.md` |
| RCC SLURM scripts | `scripts/rcc/` |
