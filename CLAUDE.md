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
- Do not add closed-source or paid-API dependencies to the core pipeline.
- ProQuest, Factiva, Bloomberg, AP News, Reuters, MarketWatch are NOT semantic corpus sources — do not reinstate without a new ADR. (AP News and Reuters were removed in ADR-010, 2026-05-11.)
- arXiv and Jackson Hole (separate ingestor) are NOT active sources — removed in ADR-012, 2026-05-13. arXiv had 2017-only coverage; Jackson Hole speeches are captured by FederalReserveIngestor.
- **IMF runs on RCC via curl_cffi + Coveo (ADR-014, 2026-05-17)** — imf.org is fronted by Akamai (not Cloudflare); the 403 ADR-013 attributed to an IP block was actually a TLS fingerprint (JA3) reject of stdlib `requests`. `IMFIngestor._imf_get` uses `curl_cffi.requests` with `impersonate='chrome131'` (verified 200 from RCC, T-Mobile cellular, and eduroam). Listing comes from the public Coveo Search endpoint (`imfproduction561s308u.org.coveo.com/rest/search/v2`); the old Sitecore JSS `_walk_publications` was replaced by series-keyed URL-prefix queries (`weo`, `gfsr`, `fandd`, `wp`, `blog`). `IMFIngestor()` is back in `InstitutionalIngestor._sub_ingestors`; no local-rsync needed. `curl_cffi==0.15.0` is in `requirements.txt` and must be installed in the RCC conda env (`mnd`).
- **After any dry-run, window change, or schema change, re-submit `submit_full_pipeline.sh` with `NUKE_RAW=1`.** Default archive mode does NOT touch `data/raw/` — including `.institutional_checkpoint.json`. A stale checkpoint from a smaller-window prior run will silently SKIP sub-ingestors marked "completed" in that prior context, producing an incomplete corpus. This bit us on 2026-05-17/18: job 49737806 was submitted with default args, loaded the May-13 2024-dry-run checkpoint, and skipped Fed/FedRegional/BIS/Treasury/OFR/VoxEU/Brookings/PIIE with 2024-only counts. Cancelled and re-submitted as job 49740251 with `NUKE_RAW=1`. The script ARCHIVES (not deletes) under archive mode, so prior data is recoverable.
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
| validate | `run_pipeline.py validate` _(all 10 anchors)_ or `validate --anchors anchor_01_svb,anchor_05_credit_suisse` _(comma-separated IDs)_. `--anchors` takes IDs, not a file path. | _(stdout only — re-run if unsure)_ |

## Phase status (update this when phases complete)

- [x] Phase 0 — scaffold, configs, anchor set, ingestors, embedding module
- [x] Phase 1 — filtering, dedup, clustering, dynamics, stages, validation, CLI
- [/] Phase 2 — full ingestion 2010–2026 RUNNING on RCC since 2026-05-18 00:11 CDT (jobs 49740251–49740257: ingest → filter-pre-embed → filter → embed primary + comparator → cluster). Fresh chain after the 2026-05-17 stale-checkpoint incident; institutional Tiers 1–2 + CFR; RavenPack dynamics layer separate; journalism tier removed per ADR-010.
- [/] Phase 3 — full corpus embedding chained behind Phase 2 (Qwen3 primary + mpnet comparator look-ahead check, ADR-011)
- [ ] Phase 4 — pre-registration finalized, full anchor + fizzled validation
- [ ] Phase 5 — Streamlit dashboard, Hugging Face Spaces deploy
- [ ] Phase 6 — weekly cron update pipeline (AP News RSS + RavenPack live)
- [ ] Phase 7 — technical report, reproducibility audit

## Environment

- Local compute: Apple Silicon MPS (MacBook Air M-series) — `embedding_device: auto` detects it
  - Set `MND_MAX_SEQ_LEN=512` in `.env` to avoid OOM on Qwen3-Embedding-0.6B (ADR-006)
- Full corpus runs: UChicago RCC (CUDA) — `MND_EMBEDDING_DEVICE=cuda` or set in `.env`; use SLURM scripts in `scripts/rcc/`
- FRED key: `FRED_API_KEY` in `.env` (validation only)
- WRDS: `WRDS_USERNAME` and `WRDS_PASSWORD` in `.env` for RavenPack dynamics layer queries
- Media Cloud: `MEDIACLOUD_API_KEY` in `.env` for Layer 2 detection

## Phase 2 corpus architecture (updated 2026-05-13, ADR-012)

### Semantic corpus (text for embedding and clustering)

| Tier | Sources | Retrieval |
|---|---|---|
| 1 — Institutional policy | Federal Reserve (all: FOMC, speeches incl. Jackson Hole, Beige Book, FEDS Notes, MPR, FSR), Regional Feds (NY/SF/Chicago/Atlanta), BIS (QR/WPs), CBO, Treasury/OFR/FSOC, Congressional testimony (Treasury Sec) | Direct fetch / institutional RSS |
| 2 — Academic analytical + policy | VoxEU/CEPR (full posts), Brookings, PIIE, CFR | Direct fetch / RSS |

**Removed from semantic corpus (ADR-010, 2026-05-11):** AP News, Reuters, MarketWatch. Their journalism propagation signal is captured by RavenPack (Layer 1B, dynamics only). Raw ingested JSONL retained in `data/raw/articles/`; excluded from embedding by `run_pipeline.py filter-pre-embed`.

**Historical corpus only (NBER, SSRN):** Historical bulk retrieval failed; both are Phase 6 live RSS only. `NBERIngestor` and `SSRNIngestor` remain in code but commented out of `InstitutionalIngestor` for historical runs.

**Stated limitation:** Premium analytical press — WSJ opinion, Bloomberg Opinion, FT — is not represented in text form. Their volume signal is captured by the RavenPack dynamics layer. Disclosed in pre-registration and methodology.

### Layer 2 — Detection (story counts only, no embedding)

**Source: Media Cloud API.** Daily story count time series by keyword/topic query across thousands of outlets. Fires candidate narrative emergence flags before institutional sources have characterized it. API key: `MEDIACLOUD_API_KEY` in `.env`. Output: `data/detection/mediacloud/`. Code: `src/mnd/detection/mediacloud.py`.

### Dynamics layer — Layer 1B (volume time series for SIR/logistic fitting)

**Source: RavenPack RPA 1.0 Global Macro, Dow Jones Edition via WRDS.**

- Metadata and event records only (not full text) for WSJ, Barron's, Dow Jones Newswires, MarketWatch, PR Newswire, and ~800 other sources
- ~5-week lag, monthly vintage by design (look-ahead bias protection). Dashboard labels all RavenPack metrics "as of [last delivered month]"
- Use for: historical volume time series on known narrative clusters; broader press propagation estimates
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
- **Source-stratified smoothing:** Before fitting, smooth each source tier (institutional / academic) separately with a centered rolling mean, then sum. The journalism tier is absent from the semantic corpus (ADR-010); `smooth.py` retains a third "journalism" bucket as a sentinel for unmapped sources only. Prevents single large institutional publications from masquerading as narrative acceleration. Store both raw and smoothed series in dynamics output. `src/mnd/dynamics/smooth.py`.
- **Economic calendar annotation:** Flag weeks within ±3 days of FOMC decisions, CPI, PCE, GDP advance, NFP, and Fed MPR releases. `calendar_event` (bool) and `calendar_event_label` (str) columns added to weekly series. Do not exclude flagged weeks from fitting — report count of flagged weeks in growth phase as a quality indicator. `src/mnd/dynamics/calendar.py`.
- **Two-stage dynamics fitting:** Parametric models only when cluster exceeds 3 articles/week avg over 4 weeks AND 50 cumulative articles. Below threshold: descriptive stats only, labeled "pre-fitting".
- **Source-type contamination check:** Flag clusters >90% one source type for manual review (post-hoc diagnostic only).

### Phase 5 dashboard design notes (locked)

**Dormant narrative display:** Dormant historical narratives must be displayed with their full fitted curves and parameters in the same visual format as active narratives. Do not gray out, visually diminish, or truncate dormant narratives. A clean SIR fit on a dormant narrative is more analytically valuable than an active narrative still in early-spread with poorly-identified R₀. Stage label (dormant / decay / peak / early-spread / pre-emergence) is displayed as an informational tag, not a quality or prominence signal.

**Calendar event markers:** Render vertical dotted lines at calendar-flagged weeks on volume curves, with event label on hover ("FOMC Meeting", "CPI Release", etc.). Users see the annotation rather than interpreting calendar-driven spikes as organic narrative growth.

**RavenPack lag labeling:** All panels sourcing data from RavenPack must display "as of [last delivered month]" prominently. Emergence detection panels source from own-corpus Tier 4 volume — label these as real-time.

**Raw vs. smoothed series:** Volume curve primary trace = smoothed_combined (stratified-smoothed). Background trace = raw_combined. Both always visible.

### Phase 2 pipeline (run on RCC, ADR-010)

```bash
# Full historical ingestion (2010-present) — SLURM dependency chain
# Journalism tier removed; single institutional job only.
INGEST=$(sbatch --parsable scripts/rcc/ingest_institutional_rcc.sh)
FILTER=$(sbatch --parsable --dependency=afterok:$INGEST scripts/rcc/filter_rcc.sh)
EMBED=$(sbatch --parsable --dependency=afterok:$FILTER scripts/rcc/embed_rcc.sh)
sbatch --dependency=afterok:$EMBED scripts/rcc/cluster_rcc.sh

# Pre-embedding filter (excludes any archived journalism sources from raw JSONL)
python scripts/run_pipeline.py filter-pre-embed

# Corpus composition QA (run after filter)
python scripts/run_pipeline.py corpus-composition --by-tier --output data/processed/corpus_composition.csv

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
| Project specification (supersedes CLAUDE.md on architecture) | `MND_PROJECT_SPEC.md` |
| Pre-registration draft | `prereg/PREREGISTRATION.md` |
| Media Cloud detection module | `src/mnd/detection/mediacloud.py` |
| RavenPack dynamics ingestor | `src/mnd/ingestion/ravenpack.py` |
| RCC SLURM scripts | `scripts/rcc/` |
| Archived / superseded code | `scripts/archive/` |
