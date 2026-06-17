# Macro Narrative Dynamics

A quantitative measurement framework for tracking how macro-financial
narratives form, propagate, peak, and decay in U.S. financial discourse from
2010 to the present. The system embeds institutional and academic documents
with a transformer encoder, clusters them into coherent narratives with
BERTopic, fits epidemiological growth models (SIR / logistic) to each
narrative's life-cycle, and surfaces the analysis through a public web
dashboard updated weekly.

This is a **descriptive measurement and educational tool**, not a prediction engine. Every parameter is a published library default or a value cited from primary literature — no researcher-tuned parameters, no sensitivity sweeps.

**For methodology, read [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) first** — plain-English walkthrough of every pipeline stage and the citation behind each choice. Then see [`MND_PROJECT_SPEC.md`](MND_PROJECT_SPEC.md) for scope and phase structure, and [`docs/architecture_decisions.md`](docs/architecture_decisions.md) for every architectural decision as a dated ADR.

## Status

- **Phase 0–1 complete.** Scaffold, configs, anchor set, ingestors, pilot clustering.
- **Phase 2 in progress.** Full 2010–present basis-set ingestion on UChicago RCC via the parallel fan-out (`scripts/rcc/submit_parallel_ingest.sh`). Awaiting one clean re-ingest with all coverage fixes baked in.
- **Phase 3+ ahead.** Re-embedding + clustering (ADR-019 methodology), anchor validation reporting, dashboard build (Phase 5), and weekly updates (Phase 6).

## Corpus architecture (ADR-020 basis set)

The semantic corpus is a **basis set**: the minimum set of sources spanning the
eight independent dimensions of US macro discourse, with no redundancy. Twelve
sub-ingestors map 1:1 to those dimensions — the dimension table and per-source
retrieval mechanics live in `docs/architecture_decisions.md` ADR-020.

| Layer | Role | Sources |
|---|---|---|
| Semantic text corpus | Embedding + clustering | Fed Board, 4 Regional Feds (NY/SF/Chicago/Atlanta), IMF, BIS, CBO, CEA, Treasury/OFR, Brookings, PIIE, NBER, VoxEU, Congressional Treasury-Sec testimony |
| 1B — Dynamics layer | Volume time series, cross-validation trace (no text) | Media Cloud premium-press collection — ADR-016/019 |
| 2 — Detection layer | Story-count anomaly flagging (no text) | Media Cloud API, broad outlet collection |
| 3 — Validation supplements | Outcome correlation, business-cycle context | FRED, NBER Business Cycle Dating |

Removed from the semantic corpus (do not reinstate without a new ADR): AP News,
Reuters, MarketWatch (ADR-010); arXiv and the separate Jackson Hole ingestor
(ADR-012); CFR (ADR-020); ProQuest TDM, GDELT, Common Crawl (ADR-010). RavenPack
/ WRDS is not used (ADR-016). Removed-ingestor code is recoverable from git history.

## Quick start

```bash
# 1. Clone and create a virtual environment
git clone <your-repo-url> macro-narrative-dynamics
cd macro-narrative-dynamics
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 2. Install dependencies (pinned in requirements.txt)
pip install -e . -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: set FRED_API_KEY (Layer 3 validation only), MEDIACLOUD_API_KEY
# (used for BOTH Layer 1B premium-press dynamics AND Layer 2 broad detection,
# ADR-016). On Apple Silicon set MND_MAX_SEQ_LEN=512 to avoid Qwen3 OOM on
# MPS (ADR-006). WRDS credentials are NOT required (RavenPack abandoned).

# 4. Run pre-flight checks
make preflight                # skips embedding model download
make preflight-full           # downloads Qwen3-Embedding-0.6B (~600 MB)
```

## Methodology choices (field-anchored)

Every parameter below is either a published library default or a citation from primary literature. The full citation list and rationale lives in [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) §10.

| Choice | Value | Anchor |
|---|---|---|
| Embedding model | `Qwen/Qwen3-Embedding-8B` (4096-d, instruction-aware) on RCC A100; `Qwen3-Embedding-0.6B` (1024-d) local-MPS fallback | MTEB benchmark; Apache 2.0 (ADR-036) |
| Embedding context | 1024 tokens (RCC) / 512 tokens (local MPS) | Hardware constraint |
| Document chunking | 512 Qwen3 tokens, ~64-token overlap | Thakur et al. 2021 *BEIR* (NeurIPS) |
| Scope filter | None pre-clustering; post-cluster JEL scope classification (drop JEL ∉ {E,F,G,H} from dynamics only) | AEA JEL Classification System (ADR-020) |
| Clustering | BERTopic with library defaults (UMAP + HDBSCAN + c-TF-IDF) | Grootendorst 2022 |
| Granularity | Single-level HDBSCAN output (no merging tiers) | Bybee/Kelly/Manela/Xiu 2024; Hansen/McMahon/Prat 2018 |
| Dynamics models | SIR and logistic | Kermack & McKendrick 1927; Verhulst 1838 |
| Smoothing window | 7-day centered moving average | Shumway & Stoffer (weekly cycle for daily counts) |
| Bayesian priors | Weakly informative, anchored to epidemic-modeling conventions | Bjørnstad 2018; Gelman et al. *BDA3* |
| Stage classification | 4 stages keyed to R₀ direction | Kermack & McKendrick 1927 (R₀=1 epidemic threshold) |
| Anchor tolerance | ±14 days | Brown & Warner 1985 (event-study convention) |
| Bootstrap replicates | 1000 | Efron & Tibshirani 1993 |
| Dedup | MinHash, 128 permutations, 0.85 Jaccard | Broder 1997; Henzinger 2006 |
| FDR threshold | 0.05 | Benjamini & Hochberg 1995 |
| Random seed | 42 throughout | Convention |

**Anchor recovery is reported as a rate, not gated by a pass/fail threshold.** Per ADR-040, no kill criteria with researcher-set thresholds, no train/test split, no formal pre-registration.

## Repository layout

```
config/                YAML configuration (locked params + outlet whitelist)
data/anchors/          Validation ground truth (10 anchor narratives + fizzled seed)
data/raw/              Ingested articles (gitignored except .gitkeep)
data/processed/        Pipeline artifacts (gitignored except .gitkeep)
src/mnd/               Python package
  ingestion/             InstitutionalIngestor composite + Fed + FRED
  processing/            Document chunker (Qwen3 SentencePiece, 512 tokens per ADR-019)
  filtering/             Date-range filter + MinHash dedup (no topic filter, ADR-020)
  embedding/             Qwen3-Embedding-8B on RCC A100, 0.6B local fallback (ADR-036)
  clustering/            BERTopic with library-default UMAP/HDBSCAN/c-TF-IDF (Grootendorst 2022); JEL scope classifier
  dynamics/              SIR + logistic + Bass + non-parametric shape facts; 7-day MA smoothing
  stages/                Life-cycle classification keyed to R₀ direction
  detection/             Media Cloud module (premium-press dynamics + broad detection)
  validation/            Anchor recovery (reporting only; no kill criteria)
  dashboard/             JSON-artifact builder feeding the Astro site (ADR-043 contract)
  utils/                 Config loader, logging
scripts/
  run_pipeline.py        CLI dispatching every stage
  preflight_check.py     Pre-flight environment validator
  rcc/                   SLURM job scripts for UChicago Midway3
web/                   Astro static site; reads the dashboard JSON artifacts at build time
docs/                  Architecture decisions, methodology, project plan PDF
tests/                 pytest suite
```

## Running pieces locally

```bash
# Per-source coverage probe for a short window (catches broken ingestors fast)
pytest tests/integration/test_source_coverage.py -m integration -v

# Single-source ingest for a short window (e.g. IMF; Coveo + curl_cffi, ADR-014)
python scripts/run_pipeline.py ingest --sources imf \
    --start 2024-09-01 --end 2024-10-31

# Captured-side coverage check (year × document_type pivot; flags cliffs/gaps)
python scripts/verify_coverage.py <source>

# Corpus composition report from raw JSONL
python scripts/run_pipeline.py corpus-composition \
    --output data/processed/corpus_composition.csv

# Pre-embedding archived-source exclusion, then date-range filter + MinHash dedup
python scripts/run_pipeline.py filter-pre-embed
python scripts/run_pipeline.py filter
```

## Full historical run (UChicago RCC)

```bash
cd /scratch/midway3/ehgarver/macro-narrative-dynamics
git pull                                                # SLURM runs the on-disk code at queue-start
NUKE_RAW=1 bash scripts/rcc/submit_parallel_ingest.sh   # archives prior outputs, then rebuilds
SOURCES="<src>" SKIP_DOWNSTREAM=1 SKIP_CLEANUP=1 \
    bash scripts/rcc/submit_parallel_ingest.sh          # re-run a single source in isolation
```

The fan-out submits one SLURM job per source (per-source `--time` budgets so no
long pole starves the rest), then chains the downstream stages on `afterok` of
every ingest job:

```
[ingest source_1 … source_N] → filter-pre-embed → filter → embed → cluster → analyze
```

`curl_cffi==0.15.0` must be installed in the RCC `mnd` conda env (`pip install -r requirements.txt`).

## Reproducibility

- Dependencies pinned in `requirements.txt`.
- Random seeds pinned in `config/config.yaml`.
- All configuration changes require a documented ADR in
  `docs/architecture_decisions.md`.
- Credibility rests on field-anchored parameters + zero hand-tuning (ADR-019,
  ADR-040), not a registered analysis plan. There is no train/test split and no
  formal pre-registration; anchor recovery is reported as a diagnostic, never gated
  or tuned toward.

## License

MIT for code. Data ingested from third-party sources retains its original
license terms; we do not redistribute raw articles, only derived analyses
(cluster assignments, life-cycle parameters, narrative summaries).
