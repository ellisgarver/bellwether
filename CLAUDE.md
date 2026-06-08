# Macro Narrative Dynamics — Claude Code Guide

## What this is

Quantitative study of narrative lifecycle dynamics in U.S. macro-financial
discourse. Pipeline: embed articles → cluster with BERTopic → fit SIR/logistic
ODEs to per-cluster volume curves → classify lifecycle stage.

- **`docs/METHODOLOGY.md`** is the canonical, plain-English methodology with the
  field-accepted citation behind each choice. **Read it first.**
- **`docs/architecture_decisions.md`** is the decision log. Every methodological
  change is gated on an ADR there. The ADR index at the top of that file marks
  which ADRs are live vs. superseded.

## Invariants (do not violate without a new ADR)

- Every threshold/hyperparameter lives in `config/config.yaml`. Never hardcode.
- Every random seed flows from `config.reproducibility.global_random_seed` (42).
- Never hand-tune any parameter to improve anchor recovery.
- Never load held-out (2020+) data into clustering or hyperparameter search before Phase 4.
- No closed-source or paid-API dependencies in the core pipeline.
- **Corpus = the ADR-020 basis set:** 12 sub-ingestors mapping 1:1 to the 8
  independent dimensions of US macro discourse (dimension table in ADR-020).
  The source selection is the *only* macro-scope constraint at ingest.
- **No pre-clustering topic filter (ADR-020).** Scope is decided post-clustering
  by `src/mnd/clustering/jel_classifier.py` (AEA JEL taxonomy, nearest-prototype
  in Qwen3 space); out-of-scope clusters (JEL ∉ {E,F,G,H}) are dropped from
  *dynamics only*, not from the embedded corpus. Do not reintroduce any
  per-source keyword/title gate.
- **Removed sources — do not reinstate without a new ADR:** ProQuest, Factiva,
  Bloomberg, AP News, Reuters, MarketWatch (journalism; ADR-010), arXiv and the
  separate Jackson Hole ingestor (ADR-012), CFR (ADR-020). RavenPack/WRDS is not
  used (ADR-016 — Media Cloud Premium replaced it).
- **Per-source retrieval mechanics and coverage-bug history live in their ADRs,
  not here.** Current ingestor behavior is whatever the code does now. When you
  fix a source, the fact belongs in one ADR + the commit message — do not restate
  it in this file.
- **Corpus correctness > convenience.** The only legitimate ingest filters are
  (a) the 2010-present window and (b) URL/content dedup. Under-capture is the
  failure mode that matters; when a hole is found, fix the ingestor so the corpus
  is correct — do not document it as a limitation.
- Any deviation from the above requires a new ADR first.

## Working style

- For each file created or significantly changed, explain in chat what it does,
  why it exists, and how it connects to adjacent modules.
- Before each continuation step, summarize what just finished and what's next —
  never start a step silently, never ask "shall I continue?" without that context.
- Never add `Co-Authored-By` lines to commits. After each task: commit
  (what / why / findings) + an ADR if it's a methodology change, then push.
- **RCC commands must be single-line** (their terminal mangles heredocs /
  multi-line paste). The user runs all SSH-to-Midway commands themselves — emit
  copy-pasteable one-liners.

## Running the pipeline

Full corpus runs on UChicago RCC (Midway3) via the parallel fan-out — one SLURM
job per source, with `filter → embed → cluster` chained on `afterok` of all
ingest jobs:

```bash
# git pull on RCC FIRST — SLURM runs the code on disk at queue-start time.
NUKE_RAW=1 bash scripts/rcc/submit_parallel_ingest.sh        # archives prior raw+processed, then rebuilds
SOURCES="<src>" SKIP_DOWNSTREAM=1 SKIP_CLEANUP=1 bash scripts/rcc/submit_parallel_ingest.sh   # re-run one source
```

- Pre-submission probe (catches silent-zero per source):
  `pytest tests/integration/test_source_coverage.py -m integration -v`
- Captured-side coverage check (year × document_type pivot, flags cliffs/gaps):
  `python scripts/verify_coverage.py <source>`
- Local spot-runs of individual stages: `make help`, or
  `python scripts/run_pipeline.py {ingest,filter-pre-embed,filter,embed,cluster,stability,validate,corpus-composition}`.

## Environment / keys (`.env`)

- Local: Apple Silicon MPS (`embedding_device: auto`); set `MND_MAX_SEQ_LEN=512`
  to avoid OOM on Qwen3-Embedding-0.6B (ADR-006).
- RCC: CUDA — `MND_EMBEDDING_DEVICE=cuda`; conda env `mnd` (`pip install -r requirements.txt`).
- `FRED_API_KEY` — validation only. `GOVINFO_API_KEY` — CEA ERP collection
  (free signup at api.govinfo.gov/signup; DEMO_KEY is rate-limited, tests only).
  `MEDIACLOUD_API_KEY` — Media Cloud dynamics/detection layers.

## Phase status

- [x] Phase 0 — scaffold, configs, anchor set, ingestors, embedding module.
- [x] Phase 1 — filtering, dedup, clustering, dynamics, stages, validation, CLI (pilot NMI=1.000; do not rerun pilot code).
- [/] Phase 2 — corpus build. First build 2026-05-18 (21,289 articles); many
  coverage bugs fixed since. Awaiting one clean `NUKE_RAW=1` re-ingest with all
  fixes + the ADR-020 basis set, then corpus-composition QA before ticking.
- [/] Phase 3 — embedding + clustering. First run 2026-05-18 (Qwen3, BERTopic,
  outlier 25.4%, stability NMI=0.880±0.003, anchor recovery 6/10 on the pre-fix
  corpus). Re-validation deferred until after the re-ingest.
- [ ] Phase 4 — pre-registration finalized; full anchor + fizzled validation.
- [ ] Phase 5 — Streamlit dashboard, Hugging Face Spaces deploy.
- [ ] Phase 6 — weekly re-ingest of the basis set + Media Cloud Premium live (ADR-016).
- [ ] Phase 7 — technical report, reproducibility audit.

## Anchor narratives (final — 10)

| # | Name | Reference date | # | Name | Reference date |
|---|---|---|---|---|---|
| 01 | SVB collapse | 2023-03-09 | 06 | Regional banking contagion | 2023-03-13 |
| 02 | COVID market crash | 2020-02-24 | 07 | 2022 inflation peak | 2022-Q2/Q3 |
| 03 | Brexit aftermath | 2016-06-24 | 08 | Soft landing emergence | 2023-Q3/Q4 |
| 04 | Transitory inflation debate | 2021-Q2 | 09 | 2013 taper tantrum | 2013-05-22 |
| 05 | Credit Suisse stress | 2023-03-15 | 10 | 2015 China devaluation scare | 2015-08-11 |

## Key file locations

| What | Where |
|---|---|
| Canonical methodology | `docs/METHODOLOGY.md` |
| Architecture decisions (decision log) | `docs/architecture_decisions.md` |
| Master config (all thresholds/seeds) | `config/config.yaml` |
| Outlet / source whitelist | `config/whitelist.yaml` |
| Anchor narratives | `data/anchors/anchor_narratives.jsonl` |
| Basis-set ingestors (composite) | `src/mnd/ingestion/institutional.py`, `fed.py` |
| Post-cluster JEL scope classifier | `src/mnd/clustering/jel_classifier.py` |
| Media Cloud dynamics + detection (not embedded) | `src/mnd/detection/mediacloud.py` |
| Pipeline CLI | `scripts/run_pipeline.py` |
| RCC SLURM scripts | `scripts/rcc/` |
| Per-source coverage tests | `tests/integration/test_source_coverage.py` |
| Captured-side coverage verifier | `scripts/verify_coverage.py` |
| Project spec (planning artifact) | `MND_PROJECT_SPEC.md` |
| Pre-registration draft | `prereg/PREREGISTRATION.md` |
