# Claude Code Handoff: Macro Narrative Dynamics

This document is the **kickoff prompt** for the Claude Code session that
continues this project. Open a Claude Code session in the repository root,
share this document, and Claude Code will have full context.

---

## Status as of handoff

Phase 0 scaffold is complete:

- ✅ Repository structure and config (`config/config.yaml` locked)
- ✅ Outlet whitelist (`config/whitelist.yaml`)
- ✅ Topic filter keywords (`config/topic_filter_keywords.yaml`)
- ✅ Anchor narratives validation set (`data/anchors/anchor_narratives.jsonl`, locked)
- ✅ Fizzled counterparts seed (`data/anchors/fizzled_counterparts_seed.jsonl`, draft)
- ✅ Pinned dependencies (`requirements.txt`)
- ✅ Working ingestors: GDELT, Federal Reserve site, FRED
- ✅ Embedding module: Qwen3 primary + mpnet comparator (ADR-001)
- ✅ Pre-flight check script
- ✅ Pre-registration template (DRAFT — finalize before Phase 4)
- ✅ Architecture decisions log (ADR-001 through ADR-004)

What remains is the **implementation** of Phases 1–7 from the project plan.

---

## Pre-flight items (human, not Claude Code)

Before starting Phase 1 build, the user must:

1. **Confirm UChicago library access** to Factiva or ProQuest News for
   paywalled-outlet full text. This is the project-killer pre-flight check
   from plan §6.1. If it fails, fall back to plan §9.1 inflation-only scope.
2. **Create the GitHub repository** and push the Phase 0 scaffold.
3. **Get a free FRED API key** at fred.stlouisfed.org/docs/api/api_key.html.
4. **Decide compute target**: UChicago RCC, local GPU, or cloud. Update
   `config.compute.embedding_device` if needed.
5. **Run pre-flight check** (`python scripts/preflight_check.py`).

When all of the above are confirmed, proceed to the Phase 1 build below.

---

## Build sequence — Phase 1: Pilot and de-risking

**Goal of Phase 1**: validate that the methodology works on a 6-month
sample before committing to full corpus ingestion. This is a kill-criterion
gate — if cluster stability or anchor recovery fails here, the project
narrows to the fallback scope.

### 1.1 Implement filtering layer (`src/mnd/filtering/`)

Create:

- `src/mnd/filtering/topic_filter.py` — hybrid keyword + embedding-similarity
  filter. Inputs: list of `Article` objects, the keyword YAML, and the
  topic-seed-articles JSONL. Outputs: filtered list with a `passed_filter`
  metadata field. Default: keyword_min_matches=2 AND embedding-similarity
  to seeds ≥ 0.55.
- `src/mnd/filtering/dedup.py` — MinHash near-duplicate detection within
  rolling 48-hour windows. Use `datasketch.MinHash` and `MinHashLSH`.
  Threshold from config (`filtering.dedup.threshold`).

The topic-seed-articles JSONL needs to be hand-curated — pick ~30 articles
from FOMC statements, WSJ macro coverage, FT Alphaville, Brookings essays,
and Project Syndicate columns that are paradigmatic of the discourse we
want to capture. Ask the user to curate this OR draft candidates from
Federal Reserve speeches (which are free).

### 1.2 Implement clustering (`src/mnd/clustering/`)

Create `src/mnd/clustering/bertopic_pipeline.py`:

- BERTopic instance with UMAP and HDBSCAN parameters from config.
- Hierarchical merging into fine/medium/coarse levels.
- Class-based TF-IDF for cluster representation with time-resolved tracking.
- `fit_transform(documents, embeddings)` interface.
- Bootstrap-stability evaluation method (NMI, ARI across 20 replicates with
  seeds 42, 43, ..., 61).

### 1.3 Implement dynamics (`src/mnd/dynamics/`)

Create:

- `src/mnd/dynamics/models.py` — pure functions for SIR ODE, logistic,
  Gompertz, exponential.
- `src/mnd/dynamics/fitting.py` — Bayesian fitting with PyMC, weakly-informative
  priors from config. AICc-based model selection per cluster.
- `src/mnd/dynamics/__init__.py` — exports.

The fitting layer needs to handle:
- Daily article-volume time series per cluster with 7-day centered MA.
- Posterior over (β, γ) for SIR; (L, k, t₀) for logistic; etc.
- Posterior credible intervals on R₀, peak time, decay rate.
- Graceful failure when convergence fails (low ESS, high R-hat) — record
  the failure in the cluster's metadata rather than crashing.

### 1.4 Implement stage classification (`src/mnd/stages/classify.py`)

Maps fitted dynamics → {pre-emergence, early-spread, peak, decay, dormant}
using thresholds from `config.stages`. Pure function over fit results.

### 1.5 Run the pilot

```bash
# Pull 6 months of GDELT for the curated whitelist
python scripts/run_pipeline.py ingest --start 2023-09-01 --end 2024-02-29

# Filter and dedupe
python scripts/run_pipeline.py filter

# Embed with primary model
python scripts/run_pipeline.py embed --role primary

# Cluster
python scripts/run_pipeline.py cluster

# Bootstrap stability
python scripts/run_pipeline.py stability

# Anchor recovery on three known recent anchors (SVB, Credit Suisse, soft landing)
python scripts/run_pipeline.py validate --anchors anchor_01_svb,anchor_07_credit_suisse,anchor_10_soft_landing
```

`scripts/run_pipeline.py` is itself a Phase 1 deliverable — implement it
as a Click-based CLI dispatching to module functions.

### 1.6 Phase 1 decision gate

Per kill criteria 1 and 2:

- If bootstrap NMI < 0.40 across all parameter settings: stop, debug, possibly fallback.
- If fewer than 2 of 3 pilot anchors recovered: stop, debug, possibly fallback.
- If both pass: commit Phase 1 results to git, proceed to Phase 2.

---

## Build sequence — Phases 2 through 7

After Phase 1 passes:

- **Phase 2**: full ingestion 2010–present (this includes paywalled outlets if
  library access confirmed). Build cross-source robustness check infrastructure
  if compute permits.
- **Phase 3**: full corpus embedding, full clustering, look-ahead sensitivity
  check (run pipeline on pre-2021 vs post-2021 sub-corpora; compare cluster
  quality). Multi-model dynamics fitting on all clusters.
- **Phase 4**: pre-registration finalized and timestamped publicly. Anchor
  recovery on full 10-narrative set. Fizzled-narrative validation. Sensitivity
  analysis across three parameter settings.
- **Phase 5**: Streamlit dashboard with two views (Life-Cycle Viewer + Emerging
  Narratives Panel). Deploy to Hugging Face Spaces.
- **Phase 6**: weekly cron-based update pipeline. Failure handling. "Last
  updated" badge.
- **Phase 7**: technical report writeup and reproducibility audit.

Detailed build items per phase are in plan §12 (`docs/Macro_Narrative_Dynamics_Project_Plan.pdf`).

---

## Working with Claude Code on this project

### Conventions

- Every implementation file has a top-level docstring explaining what it does
  and why (ties back to the plan section).
- Every config value used in code is read through `mnd.utils.config.load_config()`
  — never inlined. Changes to behavior happen by editing config, not code.
- Every numeric threshold or hyperparameter is in `config/config.yaml`.
- Every random seed flows from `config.reproducibility.global_random_seed`.
- Every file written to `data/processed/` is parquet (for tabular) or
  numpy `.npy` (for embeddings); paths come from `config.paths.*`.
- Tests live in `tests/`; every module has at minimum a smoke test.

### Anti-conventions (to avoid)

- Do NOT hand-tune any parameter to make an anchor recovery succeed.
- Do NOT modify `data/anchors/anchor_narratives.jsonl` after Phase 1 pilot
  unless adding a documented ADR.
- Do NOT load held-out (2020+) data into clustering or hyperparameter
  search before Phase 4.
- Do NOT introduce dependencies on closed-source models or paid APIs for
  the core pipeline (FRED is fine; Voyage / OpenAI / Cohere embeddings
  are not, per ADR-001).

### When to ask the user

- Topic-seed articles selection: needs human judgment.
- Fizzled-narrative confirmation post-pilot: needs human judgment.
- Outlet whitelist additions/removals: scope decision.
- Any kill-criterion trigger: stop-and-discuss.
- Any deviation from `config.yaml` or `prereg/PREREGISTRATION.md`: stop and
  document in `docs/architecture_decisions.md` first.

### Testing strategy

- Unit tests on pure functions (dynamics models, stage classification, config loading).
- Smoke tests on each ingestor (mocked HTTP responses; the real GDELT/Fed
  fetches happen in integration tests gated on a `--live` flag).
- A snapshot test for the full pilot pipeline that runs end-to-end on a
  tiny fixture corpus (~20 articles) to catch regressions.

---

## Quick prompt for the next session

When starting the Claude Code session, tell Claude:

> I'm continuing the Macro Narrative Dynamics project. Read
> `docs/handoff_to_claude_code.md` for the build plan, `docs/architecture_decisions.md`
> for the decisions already made, and the project plan PDF for full context.
> Confirm pre-flight items first (UChicago library access, GitHub repo, FRED key,
> compute target). Then proceed with Phase 1: implement filtering, clustering,
> dynamics, stage classification, and `scripts/run_pipeline.py`. Stop at each
> phase decision gate per the kill criteria.

That should be enough for Claude Code to pick up where this session leaves off
without re-deriving any of the methodological decisions.
