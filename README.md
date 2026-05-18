# Macro Narrative Dynamics

A quantitative measurement framework for tracking how macro-financial
narratives form, propagate, peak, and decay in U.S. financial discourse from
2010 to the present. The system embeds institutional and academic documents
with a transformer encoder, clusters them into coherent narratives with
BERTopic, fits epidemiological growth models (SIR/logistic/Gompertz) to each
narrative's life-cycle, and surfaces the analysis through a public web
dashboard updated weekly.

This is a **descriptive measurement system**, not a prediction engine. See
[`MND_PROJECT_SPEC.md`](MND_PROJECT_SPEC.md) for full methodology and
architecture, and [`docs/architecture_decisions.md`](docs/architecture_decisions.md)
for every architectural choice as a dated ADR.

## Status

- **Phase 0–1 complete.** Scaffold, configs, anchor set, ingestors, pilot
  clustering (NMI = 1.000, soft-landing narrative recovered).
- **Phase 2 in progress.** Full 2010–present institutional ingestion runs
  on UChicago RCC via SLURM (`scripts/rcc/submit_full_pipeline.sh`).
- **Phase 3+ ahead.** Full corpus embedding (Qwen3 primary + mpnet
  comparator look-ahead check, ADR-011), dynamics fitting, validation.

## Corpus architecture (ADR-010 / ADR-014, current)

| Layer | Role | Sources |
|---|---|---|
| 1A — Semantic text corpus | Embedding + clustering | Fed Board (FOMC, speeches incl. Jackson Hole, Beige Book, FEDS Notes, MPR, FSR), Regional Feds (NY/SF/Chicago/Atlanta/Dallas/StL/Cleveland), IMF (WEO/GFSR/F&D/WPs/Blog via Coveo + curl_cffi), BIS, CBO, Treasury/OFR/FSOC, Congressional testimony, VoxEU/CEPR, Brookings, PIIE, CFR |
| 1B — Dynamics layer | Volume time series for SIR/logistic fitting (no text) | RavenPack RPA 1.0 Global Macro via WRDS |
| 2 — Detection layer | Story-count anomaly flagging (no text) | Media Cloud API |
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
# Edit .env: set FRED_API_KEY, WRDS_USERNAME/PASSWORD (dynamics layer),
# MEDIACLOUD_API_KEY (detection layer). On Apple Silicon set
# MND_MAX_SEQ_LEN=512 to avoid Qwen3 OOM on MPS (ADR-006).

# 4. Run pre-flight checks
make preflight                # skips embedding model download
make preflight-full           # downloads Qwen3-Embedding-0.6B (~600 MB)
```

## Locked methodology choices

All values are pinned in `config/config.yaml`; do not modify without a new
ADR in `docs/architecture_decisions.md`.

| Choice | Value | Source |
|---|---|---|
| Primary embedding | `Qwen/Qwen3-Embedding-0.6B` (1024-d, 32k context) | ADR-011 |
| Comparator embedding | `all-mpnet-base-v2` (look-ahead sensitivity check only) | ADR-011 |
| `max_seq_len` (Qwen3) | 1024 (RCC V100 16 GB OOM-safe; ADR-013) | ADR-013 |
| Document chunking | 600-BPE-token chunks, 100-token overlap, > 2,000-word threshold | ADR-008 |
| Clustering | BERTopic + UMAP + HDBSCAN; fine/medium/coarse hierarchy | spec §5 Stage 4 |
| `min_cluster_size` sweep | {10, 20, 40}; production = 20 | spec §9 |
| Dynamics models | SIR (primary), logistic, Gompertz, exponential | spec §3, ADR-002 |
| Inference | PyMC, weakly-informative priors, 2000 draws × 4 chains | spec §5 Stage 5 |
| Train/holdout split | 2010–2019 train, 2020–present held-out | spec §8 Phase 4 |
| Bootstrap NMI threshold | ≥ 0.40 (kill criterion 1) | spec §11 |
| Anchor recovery threshold | ≥ 7 / 10 within 14-day tolerance (kill criterion 2) | spec §11 |
| Random seed | 42 throughout | `config/config.yaml` |

## Repository layout

```
config/                YAML configuration (locked params, whitelist, keywords)
data/anchors/          Validation ground truth (10 anchor narratives + fizzled seed)
data/raw/              Ingested articles (gitignored except .gitkeep)
data/processed/        Pipeline artifacts (gitignored except .gitkeep)
src/mnd/               Python package
  ingestion/             InstitutionalIngestor composite + Fed + FRED + RavenPack
  processing/            tiktoken-based 600-token chunker (ADR-008)
  filtering/             MinHash dedup; TopicFilter retained but not in active flow
  embedding/             Qwen3 primary + mpnet comparator
  clustering/            BERTopic pipeline with hierarchical merging + stability eval
  dynamics/              SIR / logistic / Gompertz / exponential fitting, stratified
                         smoothing, calendar annotation, volume normalization
  stages/                Five-stage life-cycle classification
  detection/             Media Cloud Layer 2 detection
  validation/            Anchor recovery
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
COMPARATOR=0 bash scripts/rcc/submit_full_pipeline.sh   # skip mpnet comparator
```

The script chains six SLURM jobs (`afterok:`):

```
ingest_institutional → filter-pre-embed → filter → embed (primary) → cluster
                                              └→ embed (comparator) (parallel)
```

`curl_cffi==0.15.0` must be installed in the RCC `mnd` conda env for IMF
fetches to clear Akamai (ADR-014).

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
