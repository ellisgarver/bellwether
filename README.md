# Macro Narrative Dynamics

A quantitative measurement framework for tracking how macro-financial narratives
form, propagate, peak, and decay in U.S. financial discourse from 2010 to the
present. The system clusters financial articles into coherent narratives using
transformer embeddings, fits epidemiological growth models to each narrative's
life-cycle, and surfaces the analysis through a public web dashboard updated
weekly.

This is a **descriptive measurement system**, not a prediction engine. See the
project plan PDF (`/docs` or attached to the repo) for full methodology and
the rationale for the descriptive framing.

## Status

**Phase 0 scaffold.** The repository contains locked configuration, the anchor
narrative validation set, working ingestion code for free sources, and stubs
for paywalled-source ingestion. Phases 1–7 are implemented in the Claude Code
session — see [`docs/handoff_to_claude_code.md`](docs/handoff_to_claude_code.md).

## Quick start

```bash
# 1. Clone and create a virtual environment
git clone <your-repo-url> macro-narrative-dynamics
cd macro-narrative-dynamics
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 2. Install dependencies (pinned)
pip install -e .              # editable install of the local package
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: set FRED_API_KEY (free at https://fred.stlouisfed.org/docs/api/api_key.html)

# 4. Run pre-flight checks
python scripts/preflight_check.py --skip-embedding   # quick check
python scripts/preflight_check.py                    # full check (downloads model)
```

If pre-flight passes, you have a working development environment. The next
step is the **paywalled-source pre-flight** (see below) — that one is a
human action, not a script.

## Critical pre-flight check

Before any pipeline work, confirm UChicago library access to **Factiva** or
**ProQuest News** for full-text retrieval of paywalled outlets. The plan
flags this as a project-killer if access fails. If you don't have access:
the pre-committed fallback narrows scope to inflation discourse only,
2018–present, using freely-available sources. See plan §9.1.

## Architecture

```
Ingestion → Filtering → Embedding → Clustering → Dynamics → Stages → Dashboard
```

Seven pipeline stages, each producing a checkpointed artifact. The full
architecture, kill criteria, and validation strategy are documented in the
project plan. Key decisions are also recorded as ADRs in
[`docs/architecture_decisions.md`](docs/architecture_decisions.md).

### Locked methodology choices (from `config/config.yaml`)

| Choice | Value | Rationale |
| --- | --- | --- |
| Primary embedding | `Qwen/Qwen3-Embedding-0.6B` | Top-tier MTEB, Apache 2.0, runnable on consumer GPU |
| Comparator embedding | `all-mpnet-base-v2` | Older cutoff for look-ahead sensitivity check |
| Clustering | BERTopic + UMAP + HDBSCAN | Standard, three-granularity hierarchy |
| Dynamics models | SIR, logistic, Gompertz, exponential | Multi-model robustness |
| Inference | PyMC, weakly-informative priors | Posterior CIs on $R_0$, peak time, decay |
| Train/test split | 2010–2019 / 2020–present | Walk-forward, no peeking |
| Anchor tolerance | 14 days (default) | Per plan §10.1 |

## Repository layout

```
config/                YAML configuration (locked parameters, whitelist, keywords)
data/anchors/          Validation ground truth (anchor & fizzled narratives)
data/raw/              Ingested articles (gitignored)
data/processed/        Pipeline artifacts (gitignored)
src/mnd/               Python package
  ingestion/             Tier A/B/C ingestors
  filtering/             Topic filter + MinHash dedup
  embedding/             Qwen3 + mpnet embedders
  clustering/            BERTopic pipeline
  dynamics/              SIR / logistic / Gompertz / exponential fitting
  stages/                Life-cycle stage classification
  validation/            Anchor recovery, bootstrap stability
  dashboard/             Streamlit dashboard
  utils/                 Config + logging
scripts/               Runnable scripts (preflight, pipeline, etc.)
prereg/                Pre-registration document
docs/                  Architecture decisions, handoff prompts
tests/                 pytest suite
```

## Reproducibility

- Dependencies pinned in `requirements.txt`
- Random seeds pinned in `config/config.yaml`
- Data snapshots archived to `data/snapshots/` per Phase 2
- All configuration changes require a documented ADR in `docs/architecture_decisions.md`
- Pre-registration document in `prereg/PREREGISTRATION.md` is committed to a
  public timestamp **before** any held-out validation runs

## Running pieces standalone

```bash
# Discover articles from GDELT for a date range (no full text)
python -c "
from datetime import date
from mnd.ingestion import GdeltIngestor
g = GdeltIngestor()
for art in list(g.fetch(date(2024,1,1), date(2024,1,2)))[:5]:
    print(art.source_id, art.title[:80])
"

# Pull a Federal Reserve speech archive
python -c "
from datetime import date
from mnd.ingestion import FederalReserveIngestor
f = FederalReserveIngestor()
for art in list(f.fetch(date(2023,3,1), date(2023,3,31)))[:3]:
    print(art.title)
"

# Pull macro validation data from FRED
python -c "
from mnd.ingestion import FredFetcher
df = FredFetcher().fetch(start='2023-01-01', end='2023-12-31')
print(df.tail())
"
```

## Citing the project

When the technical report is published, cite as documented there. Until
then, cite the GitHub repository directly.

## License

MIT for code. Data ingested from third-party sources retains its original
license terms; we do not redistribute raw articles, only derived analyses
(clusters, life-cycle parameters, narrative summaries).
