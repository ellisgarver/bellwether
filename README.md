# Macro Narrative Dynamics

A quantitative measurement framework for tracking how macro-financial
narratives form, propagate, peak, and decay in U.S. financial discourse from
2010 to the present. The system embeds institutional and academic documents
with a transformer encoder, clusters them into coherent narratives with
BERTopic, fits epidemiological growth models (SIR/logistic/Gompertz) to each
narrative's life-cycle, and surfaces the analysis through a public web
dashboard updated weekly.

This is a **descriptive, educational, historical, and analytical measurement system**, not a prediction engine. The methodology is anchored throughout to field-accepted citations or published library defaults — no researcher-tuned parameters, no sensitivity sweeps.

**For methodology, read [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) first** — plain-English walkthrough of every pipeline stage and the citation behind each choice. Then see [`MND_PROJECT_SPEC.md`](MND_PROJECT_SPEC.md) for scope and phase structure, and [`docs/architecture_decisions.md`](docs/architecture_decisions.md) for every architectural decision as a dated ADR.

## Status

- **Phase 0–1 complete.** Scaffold, configs, anchor set, ingestors, pilot clustering.
- **Phase 2 in progress.** Full 2010–present institutional ingestion on UChicago RCC via SLURM (`scripts/rcc/submit_full_pipeline.sh`). Methodology lock-in (ADR-019) pending before final re-ingest.
- **Phase 3+ ahead.** Re-embedding + clustering with ADR-019 methodology, then anchor validation reporting, dashboard build (Phase 5), and weekly cron updates (Phase 6).

## Corpus architecture (ADR-010 / ADR-014 / ADR-015 / ADR-016, current)

| Layer | Role | Sources |
|---|---|---|
| 1A — Semantic text corpus | Embedding + clustering | Fed Board (FOMC, speeches incl. Jackson Hole, Beige Book, FEDS Notes, MPR, FSR), Regional Feds (NY/SF/Chicago/Atlanta/Dallas/StL/Cleveland), IMF (WEO/GFSR/F&D/WPs/Blog via Coveo + curl_cffi), BIS, CBO, Treasury/OFR/FSOC, Congressional testimony, VoxEU/CEPR, Brookings, PIIE, CFR |
| 1B — Dynamics layer | Volume time series for SIR/logistic fitting (no text) | Media Cloud premium-press collection (WSJ, Bloomberg, FT, Reuters, NYT, Barron's, Dow Jones, MarketWatch, AP Business, etc.) — ADR-016 |
| 2 — Detection layer | Story-count anomaly flagging (no text) | Media Cloud API, broad outlet collection |
| 3 — Validation supplements | Outcome correlation, business-cycle context | FRED, EPU (Baker-Bloom-Davis), NBER Business Cycle Dating |

Permanently removed from the semantic corpus (do not reinstate without a new
ADR): AP News, Reuters, MarketWatch (ADR-010); arXiv, separate Jackson Hole
ingestor (ADR-012); ProQuest TDM, NewsAPI, GDELT, Common Crawl (ADR-010
archived). Archived code lives in `scripts/archive/`.

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
| Embedding model | `Qwen/Qwen3-Embedding-0.6B` (1024-d, instruction-aware) | MTEB benchmark; Apache 2.0 |
| Embedding context | 1024 tokens (RCC) / 512 tokens (local MPS) | Hardware constraint |
| Document chunking | 512 Qwen3 tokens, ~64-token overlap | Thakur et al. 2021 *BEIR* (NeurIPS) |
| Filter | JEL-anchored keyword list (213 keywords, 11 categories), ≥2 matches | AEA JEL Classification System |
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

**Anchor recovery is reported as a rate, not gated by a pass/fail threshold.** Per ADR-019, no kill criteria with researcher-set thresholds.

## Repository layout

```
config/                YAML configuration (locked params, whitelist, keywords)
data/anchors/          Validation ground truth (10 anchor narratives + fizzled seed)
data/raw/              Ingested articles (gitignored except .gitkeep)
data/processed/        Pipeline artifacts (gitignored except .gitkeep)
src/mnd/               Python package
  ingestion/             InstitutionalIngestor composite + Fed + FRED
  processing/            Document chunker (Qwen3 SentencePiece, 512 tokens per ADR-019)
  filtering/             JEL-anchored canonical topic filter + MinHash dedup
  embedding/             Qwen3-Embedding-0.6B (sole embedder, ADR-019)
  clustering/            BERTopic with library-default UMAP/HDBSCAN/c-TF-IDF (Grootendorst 2022)
  dynamics/              SIR + logistic fitting; 7-day MA smoothing; calendar annotation
  stages/                Four-stage life-cycle classification (R₀-keyed)
  detection/             Media Cloud module (Layer 1B premium dynamics + Layer 2 broad detection)
  validation/            Anchor recovery (reporting only; no kill criteria)
  dashboard/             Streamlit dashboard (Phase 5)
  utils/                 Config loader, logging
scripts/
  run_pipeline.py        CLI dispatching every stage
  preflight_check.py     Pre-flight environment validator
  smoke_test_checkpoint.py  Smoke test for InstitutionalIngestor resume logic
  rcc/                   SLURM job scripts for UChicago Midway3
  archive/               Removed sources (AP News, MarketWatch, Reuters, arXiv,
                         GDELT, NewsAPI, ProQuest TDM, tdm_studio_export)
prereg/                Pre-registration document
docs/                  Architecture decisions, deviations, project plan PDF
tests/                 pytest suite
```

## Running pieces locally

```bash
# Probe institutional sources for a short window (catches broken ingestors fast)
python scripts/run_pipeline.py sample-check --source institutional \
    --start 2024-09-01 --end 2024-10-31 --max-per-source 5

# IMF-only debug probe (Coveo + curl_cffi path; ADR-014)
python scripts/run_pipeline.py ingest --sources imf \
    --start 2024-09-01 --end 2024-10-31

# Corpus composition report from raw JSONL
python scripts/run_pipeline.py corpus-composition --by-tier \
    --output data/processed/corpus_composition.csv

# Pre-embedding archived-source exclusion (writes corpus_for_embedding.jsonl)
python scripts/run_pipeline.py filter-pre-embed

# Date-range filter + MinHash dedup (writes articles.parquet)
python scripts/run_pipeline.py filter
```

## Full historical run (UChicago RCC)

```bash
cd /scratch/midway3/ehgarver/macro-narrative-dynamics
bash scripts/rcc/submit_full_pipeline.sh                # 2010-today, archives prior outputs
START=2010-01-01 END=2025-12-31 \
    bash scripts/rcc/submit_full_pipeline.sh            # custom window
NUKE_RAW=1 bash scripts/rcc/submit_full_pipeline.sh     # required on re-submit (see CLAUDE.md)
```

The script chains four SLURM jobs (`afterok:`):

```
ingest_institutional → filter → embed → cluster
```

`curl_cffi==0.15.0` and `playwright==1.48.0` (with Chromium installed) must be installed in the RCC `mnd` conda env — see `scripts/install_playwright_for_cbo.sh` for one-time CBO setup.

## Reproducibility

- Dependencies pinned in `requirements.txt`.
- Random seeds pinned in `config/config.yaml`.
- All configuration changes require a documented ADR in
  `docs/architecture_decisions.md`.
- `prereg/PREREGISTRATION.md` is committed to a public timestamp before any
  held-out (2020+) validation run.

## License

MIT for code. Data ingested from third-party sources retains its original
license terms; we do not redistribute raw articles, only derived analyses
(cluster assignments, life-cycle parameters, narrative summaries).
