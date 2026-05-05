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
- ProQuest, Factiva, Reuters, Bloomberg are NOT pipeline sources — do not reinstate.
- Any deviation from the above requires a new ADR in `docs/architecture_decisions.md` first.

## Communication style

- For every file created or significantly modified, explain in chat what it does, why it exists, and how it connects to adjacent modules.
- Before every continuation step, summarize what was just completed and what the next step will do — never start a new step silently.
- Never say "shall I continue?" without that context attached.
- Never add Co-Authored-By lines to commit messages.

## Resuming a mid-pilot session

Phase 1 pilot is **complete** (NMI=1.000, soft landing recovered). Do not rerun or
modify pilot code. Resume instructions below are retained for reference only.

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

## Phase status (update this when phases complete)

- [x] Phase 0 — scaffold, configs, anchor set, ingestors, embedding module
- [x] Phase 1 — filtering, dedup, clustering, dynamics, stages, validation, CLI
- [ ] Phase 2 — full ingestion 2010–present (institutional + AP News + RavenPack dynamics layer)
- [ ] Phase 3 — full corpus embedding, look-ahead sensitivity, multi-model dynamics
- [ ] Phase 4 — pre-registration finalized, full anchor + fizzled validation
- [ ] Phase 5 — Streamlit dashboard, Hugging Face Spaces deploy
- [ ] Phase 6 — weekly cron update pipeline (AP News RSS + RavenPack live)
- [ ] Phase 7 — technical report, reproducibility audit

## Environment

- Local compute: Apple Silicon MPS (MacBook Air M-series) — `embedding_device: auto` detects it
  - Set `MND_MAX_SEQ_LEN=512` in `.env` to avoid OOM on Qwen3-Embedding-0.6B (see ADR-006)
  - `config.yaml` now defaults to 32768; the env var overrides for local runs without touching the file
- Full corpus runs: UChicago RCC (CUDA) — `MND_EMBEDDING_DEVICE=cuda` or set in `.env`; use SLURM scripts in `scripts/rcc/`
- FRED key: `FRED_API_KEY` in `.env` (validation only)
- WRDS: `WRDS_USERNAME` and `WRDS_PASSWORD` in `.env` for RavenPack dynamics layer queries

## Phase 2 corpus architecture (FINAL — finalized 2026-05-04)

### Semantic corpus (text for embedding and clustering)

| Tier | Sources | Retrieval |
|---|---|---|
| 1 — Institutional policy | Federal Reserve (all: FOMC, speeches, regional Feds), IMF (WEO/GFSR/WPs/Blog), BIS (QR/WPs), CEA, CBO, Treasury/OFR/FSOC | Direct fetch / institutional RSS |
| 2 — Academic analytical | NBER WPs (abstracts + intros), SSRN macro/finance (abstracts), VoxEU/CEPR (full posts) | Direct fetch / RSS |
| 3 — Policy-journalism bridge | Brookings Institution, PIIE (Peterson Institute) | Direct fetch / RSS |
| 4 — Open journalism | AP News (wire, event detection, 2010–present); MarketWatch (analytical/interpretive, 2010–present; consistent from 2015 onward) | Wayback CDX (historical); RSS (Phase 6 live) |

**Stated limitation:** Premium analytical press — WSJ opinion, Bloomberg Opinion, FT — is not represented in text form. Their volume signal is partially captured by the RavenPack dynamics layer (Dow Jones edition covers WSJ, DJN, Barron's, MarketWatch). Disclosed in pre-registration and methodology. Not a gap to patch.

**MarketWatch pre-2015 coverage note:** Wayback CDX coverage of MarketWatch thins before 2015. Corpus composition QA flags pre-2015 MarketWatch records (`sparse_wayback_coverage=True` in raw_metadata). Treat as consistent from 2015-01-01 onward for cross-year comparison.

### Dynamics layer (volume time series for SIR/logistic fitting)

**Source: RavenPack RPA 1.0 Global Macro, Dow Jones Edition via WRDS.**

- Metadata and event records only (not full text) for WSJ, Barron's, Dow Jones Newswires, MarketWatch, PR Newswire, and ~800 other sources
- ~5-week lag, monthly vintage by design (look-ahead bias protection). Dashboard labels all RavenPack metrics "as of [last delivered month]"
- Use for: historical volume time series on known narrative clusters; broader press propagation estimates
- Emergence detection uses own-corpus volume counts from Tier 4 journalism — real-time signal
- Do NOT feed RavenPack records into embedding or clustering — dynamics layer only

### Anchor narratives (FINAL — 10 narratives)

| # | Name | Reference date |
|---|---|---|
| 01 | SVB collapse | 2023-03-09 |
| 02 | COVID market crash | 2020-02-24 |
| 03 | Brexit aftermath | 2016-06-24 |
| 04 | Transitory inflation debate | 2021-Q2 |
| 05 | Credit Suisse stress | 2023-03-15 |
| 06 | Regional banking contagion | 2023-03-13 |
| 07 | 2022 inflation peak narrative | 2022-Q2/Q3 |
| 08 | Soft landing emergence | 2023-Q3/Q4 |
| 09 | 2013 taper tantrum | 2013-05-22 |
| 10 | 2015 China devaluation scare | 2015-08-11 |

Removed from prior version: FTX collapse, GameStop short squeeze (out of macro scope).

### Locked architectural decisions

- **Timestamps:** Publication/release date throughout. FOMC minutes = release date.
- **Document chunking:** Docs >2,000 words split into 600-token chunks, 100-token overlap. Count by document (not chunk) for dynamics.
- **Volume normalization:** Weekly counts per cluster / total corpus articles that week, before SIR/logistic fitting.
- **Source-stratified smoothing:** Before fitting, smooth each source tier (institutional / academic / journalism) separately with a centered rolling mean, then sum. Prevents single large institutional publications from masquerading as narrative acceleration. Store both raw and smoothed series in dynamics output. `src/mnd/dynamics/smooth.py`.
- **Economic calendar annotation:** Flag weeks within ±3 days of FOMC decisions, CPI, PCE, GDP advance, NFP, and Fed MPR releases. `calendar_event` (bool) and `calendar_event_label` (str) columns added to weekly series. Do not exclude flagged weeks from fitting — report count of flagged weeks in growth phase as a quality indicator. `src/mnd/dynamics/calendar.py`.
- **Two-stage dynamics fitting:** Parametric models only when cluster exceeds 3 articles/week avg over 4 weeks AND 50 cumulative articles. Below threshold: descriptive stats only, labeled "pre-fitting".
- **Source-type contamination check:** Flag clusters >90% one source type for manual review (post-hoc diagnostic only).

### Phase 5 dashboard design notes (locked)

**Dormant narrative display:** Dormant historical narratives must be displayed with their full fitted curves and parameters in the same visual format as active narratives. Do not gray out, visually diminish, or truncate dormant narratives. A clean SIR fit on a dormant narrative is more analytically valuable than an active narrative still in early-spread with poorly-identified R₀. Stage label (dormant / decay / peak / early-spread / pre-emergence) is displayed as an informational tag, not a quality or prominence signal.

**Calendar event markers:** Render vertical dotted lines at calendar-flagged weeks on volume curves, with event label on hover ("FOMC Meeting", "CPI Release", etc.). Users see the annotation rather than interpreting calendar-driven spikes as organic narrative growth.

**RavenPack lag labeling:** All panels sourcing data from RavenPack must display "as of [last delivered month]" prominently. Emergence detection panels source from own-corpus Tier 4 volume — label these as real-time.

**Raw vs. smoothed series:** Volume curve primary trace = smoothed_combined (stratified-smoothed). Background trace = raw_combined. Both always visible.

### Phase 2 pipeline (run on RCC)

```bash
# Full historical ingestion (2010-present)
sbatch scripts/rcc/ingest_rcc.sh          # institutional + AP News (Wayback CDX)

# Filter, chunk, embed, cluster
python scripts/run_pipeline.py filter
python scripts/run_pipeline.py chunk
python scripts/run_pipeline.py corpus-composition --by-tier --output data/processed/corpus_composition.csv
sbatch scripts/rcc/embed_rcc.sh
sbatch scripts/rcc/cluster_rcc.sh

# Dynamics layer (RavenPack via WRDS — separate from semantic corpus)
python scripts/run_pipeline.py ingest-dynamics --start 2010-01-01 --end auto
python scripts/run_pipeline.py smooth-dynamics        # source-stratified smoothing
python scripts/run_pipeline.py annotate-calendar      # ±3d economic calendar flags
python scripts/run_pipeline.py normalize-dynamics
```

## Key file locations

| What | Where |
|---|---|
| Master config (locked) | `config/config.yaml` |
| Outlet / source whitelist | `config/whitelist.yaml` |
| Topic filter keywords | `config/topic_filter_keywords.yaml` |
| Anchor narratives (locked) | `data/anchors/anchor_narratives.jsonl` |
| Topic seed articles | `data/anchors/topic_seed_articles.jsonl` |
| Architecture decisions | `docs/architecture_decisions.md` |
| Pre-registration draft | `prereg/PREREGISTRATION.md` |
| RCC SLURM scripts | `scripts/rcc/` |
| Archived / superseded code | `scripts/archive/` |
