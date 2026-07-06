# Macro Narrative Dynamics

An educational tool for tracking how macro-financial narratives form, propagate,
peak, and decay in U.S. institutional and academic discourse from 2010 to the
present. The system embeds documents with a transformer encoder, clusters them
into coherent narratives with BERTopic, reads each narrative's life-cycle stage
directly from its attention trajectory (a model-free trend test), and surfaces
the analysis through a public web dashboard. Epidemic (SIR), logistic, and
adoption (Bass) curves are fit alongside as interpretive lenses — shown together,
never used to pick a winner or to set the stage.

A descriptive, historical measurement tool. Every parameter is a published
library default or a value drawn from primary literature.

**For methodology, read [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) first** — a
plain-English walkthrough of every pipeline stage and the citation behind each
choice.

## Corpus architecture

The semantic corpus is a basis set spanning the eight independent dimensions of
U.S. macro discourse plus a cross-cutting question-and-answer register
(Congressional testimony by the Treasury Secretary). Twelve sub-ingestors
populate this basis set; the financial press is tracked separately as a volume
overlay and is never embedded.

| Layer | Role | Sources |
|---|---|---|
| Semantic text corpus | Embedding, clustering, dynamics fitting | Fed Board, 4 Regional Feds (NY/SF/Chicago/Atlanta), IMF, BIS, CBO, CEA, Treasury/OFR, Brookings, PIIE, NBER, VoxEU, Congressional Treasury-Sec testimony |
| Press overlay | Story-count time series and discourse-vs-press lead/lag, display and validation only (no text) | Media Cloud |
| Markets overlay | Market-series vs discourse lead/lag, display and validation only (no text) | FRED |
| Validation | Outcome correlation, business-cycle context | FRED, NBER Business Cycle Dating |

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
# Edit .env: set FRED_API_KEY (validation and markets overlay) and MEDIACLOUD_API_KEY
# (press overlay). On Apple Silicon, set MND_MAX_SEQ_LEN=512 to avoid Qwen3 OOM on MPS.

# 4. Run pre-flight checks
make preflight                # skips embedding model download
make preflight-full           # downloads Qwen3-Embedding-0.6B (~600 MB)
```

## Methodology choices (field-anchored)

Every parameter below is either a published library default or a citation from
primary literature. The full citation list and rationale lives in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

| Choice | Value | Anchor |
|---|---|---|
| Embedding model | `Qwen/Qwen3-Embedding-8B` (4096-d, instruction-aware) on RCC A100; `Qwen3-Embedding-0.6B` (1024-d) local-MPS fallback | MTEB benchmark; Apache 2.0 |
| Max sequence length | 1024 tokens (RCC) / 512 tokens (local MPS) | Hardware constraint |
| Document chunking | 512 Qwen3 tokens, ~64-token overlap | Thakur et al. 2021 *BEIR* (NeurIPS) |
| Scope filter | None pre-clustering; post-cluster JEL classification flags out-of-scope clusters (JEL ∉ {E,F,G,H}) without dropping them | AEA JEL Classification System |
| Clustering | BERTopic with library defaults (UMAP + HDBSCAN + c-TF-IDF) | Grootendorst 2022 |
| Granularity | Single-level HDBSCAN output (no merging tiers) | Bybee/Kelly/Manela/Xiu 2024; Hansen/McMahon/Prat 2018 |
| Dynamics models | SIR, logistic, Bass, model-free shape facts | Kermack & McKendrick 1927; Verhulst 1838; Bass 1969 |
| Smoothing window | 7-day centered moving average | Shumway & Stoffer (weekly cycle for daily counts) |
| Lens fitting | Bounded least-squares point fits, each reported with R²; weak fits shown grayed, never hidden | scipy; Schlickeiser & Kröger 2020 (closed-form SIR) |
| Stage classification | Model-free: 4 stages (growth / stable / decay / dormant) from a trend + level test on the volume curve | Mann 1945; Kendall 1948; Hamed & Rao 1998 |
| Anchor tolerance | ±14 days | Brown & Warner 1985 (event-study convention) |
| Bootstrap replicates | 1000 | Efron & Tibshirani 1993 |
| Dedup | MinHash over character 5-grams, 128 permutations, Jaccard 0.85 | Broder 1997; Henzinger 2006 |
| FDR threshold | 0.05 | Benjamini & Hochberg 1995 |
| Random seed | 42 throughout | Convention |

Anchor recovery is reported as a diagnostic rate; no parameter is tuned toward it.

## Repository layout

```
config/                YAML configuration (locked params + outlet whitelist)
data/anchors/          Validation ground truth (10 anchor narratives + fizzled seed)
data/raw/              Ingested articles (gitignored except .gitkeep)
data/processed/        Pipeline artifacts (gitignored except .gitkeep)
src/mnd/               Python package
  ingestion/             InstitutionalIngestor composite + Fed + FRED
  processing/            Document chunker (Qwen3 SentencePiece, 512 tokens)
  filtering/             Date-range filter + MinHash dedup
  embedding/             Qwen3-Embedding-8B on RCC A100, 0.6B local fallback
  clustering/            BERTopic (UMAP/HDBSCAN/c-TF-IDF) + JEL scope classifier
  dynamics/              SIR + logistic + Bass least-squares fits + model-free shape facts; 7-day MA smoothing
  stages/                Model-free life-cycle classification (trend + level test)
  detection/             Press (Media Cloud) and markets (FRED) overlays — display and validation, no text
  validation/            Anchor recovery (reporting only)
  dashboard/             JSON-artifact builder feeding the Astro site
  utils/                 Config loader, logging
scripts/
  run_pipeline.py        CLI dispatching every stage
  preflight_check.py     Pre-flight environment validator
  rcc/                   SLURM job scripts for UChicago Midway3
web/                   Astro static site; reads the dashboard JSON artifacts at build time
docs/                  Methodology, architecture decisions, project plan
tests/                 pytest suite
```

## Running pieces locally

```bash
# Per-source coverage probe for a short window (catches broken ingestors fast)
pytest tests/integration/test_source_coverage.py -m integration -v

# Single-source ingest for a short window (e.g. IMF)
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
cd /scratch/midway3/$USER/macro-narrative-dynamics
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

The SLURM fan-out is the **full-rebuild** path (GPU embed of the whole corpus). It
is RCC-convenient but not required — everything it does is also reachable through
the portable per-stage commands above and the `update` command below.

## Weekly updates (portable — no RCC, no GPU, no SLURM)

The weekly refresh is a single, self-contained command that runs anywhere Python
does — a laptop, a small cron VM, GitHub Actions, or an RCC login/compute node:

```bash
python scripts/run_pipeline.py update
```

It advances each source from its own last-captured date (over-fetching a buffer so
staggered per-source frontiers leave no gap; dedup absorbs the overlap), then
re-bakes the dashboard artifacts — refreshing the **Media Cloud press layer** and
the **press-heating** emerging signal against the current narrative set. Because
the delta is small and embedding is incremental, it is CPU-minutes, not GPU-hours.

> Identity-stable institutional re-clustering is built and validated (BERTopic
> `merge_models` with an anchor-id gate, ADR-066) but not yet wired into `update`,
> so newly-ingested institutional articles are **parked** until the next full
> rebuild and the narrative *set* is "as of the last full build". The live
> movement between rebuilds comes from the press layer.

**Data location.** By default all data lives under `data/` in the repo, so a fresh
clone needs no configuration. To put data elsewhere (e.g. RCC scratch, off the home
quota), set `MND_DATA_ROOT`:

```bash
export MND_DATA_ROOT=/scratch/$USER/mnd-data      # optional; defaults to the repo
```

**Scheduling** is left to you — the command is backend-agnostic. Pick whichever
runner fits your environment:

```bash
# cron (weekly, Monday 06:00) — a laptop or a VM
0 6 * * 1  cd /path/to/macro-narrative-dynamics && python scripts/run_pipeline.py update >> logs/update.log 2>&1

# systemd timer: an update.service running the command + an update.timer OnCalendar=weekly

# GitHub Actions: on: schedule: - cron: "0 6 * * 1"  →  run the command (set MEDIACLOUD_API_KEY as a secret)

# RCC: a login-node crontab entry, or an sbatch --begin=... resubmitting weekly
```

Set `MEDIACLOUD_API_KEY` for the press layer; without it, `update` still refreshes
everything else and simply omits the press sections.

## Building the site

The public site is a static Astro build (`web/`) that reads the baked JSON
artifacts at build time — the browser never fetches or computes:

```bash
python scripts/run_pipeline.py analyze   # bake data/processed/dashboard/ (or use `update`)
cd web
npm ci
npm run dev        # local dev server
npm run build      # static site in web/dist
```

The build reads `data/processed/dashboard/` by default; set `DASHBOARD_DATA_DIR`
to point elsewhere. Narrative display names come from the naming layer during the
bake — a local Ollama serving `llama3.1` by default, or any OpenAI-compatible
endpoint via `MND_NAMING_BASE_URL` / `MND_NAMING_MODEL` / `MND_NAMING_API_KEY`.
Generated names are cached and committed (`data/naming_cache/`), so rebuilds are
deterministic and only new or changed narratives call the model.

## Reproducibility

- Dependencies pinned in `requirements.txt`.
- Random seeds pinned in `config/config.yaml` (seed 42 throughout).
- Every parameter is a published default or a cited value; anchor recovery is
  reported as a diagnostic, never tuned toward.

## License

MIT for code. Data ingested from third-party sources retains its original
license terms. Raw articles are not redistributed; only derived analyses
(cluster assignments, life-cycle parameters, narrative summaries) are published.
