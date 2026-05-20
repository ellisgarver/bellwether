# Macro Narrative Dynamics — Full Project Specification

> ## ⚠️ Document status (as of 2026-05-19)
>
> **The canonical methodology reference is now `docs/METHODOLOGY.md`** — a plain-English walkthrough of every pipeline stage and the field-accepted citation behind each methodological choice.
>
> This spec remains the operational reference for **scope, source list, anchor narratives, phase structure, and project framing** (sections 1-2, 4-5, 7-8). The methodology subsections of section 3 are PARTIALLY SUPERSEDED by subsequent ADRs (012, 015, 016, 017, 018, 019). Where this document and METHODOLOGY.md disagree on methodology, METHODOLOGY.md is canonical.
>
> Specifically superseded:
> - Stage 3 Embedding — the **comparator (mpnet) look-ahead sensitivity check** is removed (ADR-019). The comparator architecture is a sensitivity-check apparatus that the new methodology principle (anchored-or-removed) excludes. Qwen3-Embedding-0.6B is the sole embedder.
> - Stage 3 Embedding — chunking is **512 Qwen3 tokens with ~64-token overlap** (BEIR convention; Thakur et al. 2021), not 600 cl100k tokens with 100-token overlap. The chunker uses Qwen3's own SentencePiece tokenizer.
> - Stage 4 Clustering — **single granularity** (BERTopic library-default HDBSCAN output, Grootendorst 2022). The three-tier "fine/medium/coarse" hierarchy with silhouette thresholds 0.30/0.45/0.60 is removed (ADR-019).
> - Stage 4 Clustering — **no sensitivity sweep** on `hdbscan.min_cluster_size`. Fixed at the BERTopic library default of 10.
> - Stage 4 Clustering — **no kill criterion** on NMI < 0.40. NMI is reported, not gated.
> - Stage 5 Dynamics — **single 7-day centered MA on combined volume** (Shumway & Stoffer); source-stratified smoothing removed as researcher-introduced complexity without literature anchor.
> - Stage 5 Dynamics — Institutional discourse is the **primary** volume signal (where narrative formation happens); Media Cloud premium and broad press are **secondary/cross-validation** signals (ADR-016 framing).
> - Stage 6 Stages — **four stages** keyed to R₀ direction: pre-emergence, growth (R₀>1), decay (R₀<1), dormant. The arbitrary ±14d peak window, -30% decay threshold, ≤1/day dormant threshold are removed.
> - Stage 7 Dashboard — **three pages** (Emerging Narratives, Narrative Landscape 2D UMAP, Timeline), not two. Each narrative card surfaces top-5 most-similar past narratives by three measures (semantic centroid cosine, top-term Jaccard, growth-curve Pearson). Per-narrative drill-down + compare mode + anchor validation transparency.
> - Section 11 (Kill Criteria) — **no pass/fail kill criteria** on anchor recovery rate or bootstrap NMI. Rates are reported as outputs; no binary thresholds.
>
> **Read METHODOLOGY.md first; treat the methodology subsections of this document as historical record where they disagree.**

---

## 1. What This Project Is

A quantitative measurement framework for tracking how macro-financial narratives form, propagate, peak, and decay in U.S. financial discourse from 2010 to the present. The system clusters documents into coherent narratives using transformer-based semantic embeddings, fits epidemiological growth models to each narrative's life-cycle, and surfaces the analysis through a public web dashboard updated weekly.

This is a **descriptive, historical measurement system**. It is not a predictive trading tool and makes no causal claims. The framing is deliberately observational: the value is helping users understand how financial discourse evolves, not betting on its consequences. This framing is methodologically important — it sidesteps reverse-causality and causal-inference problems that would undermine any predictive version of this work.

**Core intellectual contribution:** Operationalizing Robert Shiller's narrative economics framework (Shiller 2017, 2019) with modern NLP tooling, applied with rigorous methodology. Narrative economics has remained largely qualitative since Shiller's foundational work. This project brings quantitative measurement to it and deploys it as a live public tool.

**One-sentence pitch:** Macro narratives about inflation, recession, and monetary policy spread through analytical and institutional writing in patterns resembling epidemics — this system measures those dynamics, characterizes narrative life-cycles, and surfaces emerging patterns with historical analogs.

---

## 2. Scope

**In scope:**
- Macro-financial narrative discourse: inflation expectations, recession and business-cycle framing, monetary policy narratives, major macro shocks and their analytical aftermath (banking stress, supply disruptions, geopolitical events with macro-financial dimensions)
- U.S. financial and institutional discourse in English, 2010 to present
- U.S. press coverage of foreign events is in scope; foreign-language coverage is not

**Out of scope:**
- Single-stock analyst commentary
- Sector narratives without macro implications
- Pure technical-trading commentary
- Cryptocurrency outside macro-relevant framing
- Causal claims about market outcomes
- Predictive trading signals
- Non-English or non-U.S. primary sources

---

## 3. Theoretical Framework

The core model treats narratives as epidemic phenomena following the SIR (Susceptible–Infected–Recovered) framework. Each narrative is an infectious idea spreading through a discourse community. The basic reproduction number R₀ = β/γ characterizes transmissibility: R₀ > 1 means the narrative is growing, R₀ < 1 means it is dying out. Life-cycle stages — emergence, exponential growth, peak, decay — are all observable in document-volume time series.

Multiple parametric models are fit in parallel per narrative cluster:
- **SIR/SEIR** — epidemiologically motivated, primary model
- **Logistic growth** — f(t) = L / (1 + e^(-k(t-t₀))), robust fallback; always fit regardless
- **Gompertz growth** — asymmetric peak, common in diffusion modeling
- **Simple exponential** — baseline for very early-stage narratives

If SIR fits poorly across the validation set, fall back to logistic growth or non-parametric raw curve features (peak velocity, time-to-peak, decay slope). Logistic is the MVP fallback.

---

## 4. Data Source Architecture — FINAL

**This supersedes all prior corpus architecture. The following are permanently removed from active ingestion (historical AND Phase 6 live): AP News, MarketWatch, GDELT, Common Crawl, ProQuest, NewsAPI, arXiv, Jackson Hole papers as a separate source, NBER, SSRN. Media Cloud Premium Press is the journalism coverage layer (Layer 1B). Media Cloud broad outlets is the detection layer (Layer 2). JLN uncertainty indices are replaced by EPU. RavenPack is NOT used (ADR-016, 2026-05-18). Phase 6 = Tier 1/2 re-ingest + Media Cloud Premium only; nothing new added in live (ADR-017, 2026-05-18).**

The architecture maps directly onto Shiller's narrative propagation framework: narratives are characterized in analytical institutional discourse (Layer 1A text), propagate into financial journalism (Layer 1B Media Cloud Premium Press), and their emergence is detected via broad volume signals before institutional characterization begins (Layer 2). These layers are operationally separate — Media Cloud does not feed text embedding or clustering at either layer; both layers consume the same Media Cloud API with different outlet-collection scopes.

---

### Layer 1A — Semantic Text Corpus (embedding and clustering)

All sources are free, open access, and programmatically retrievable. No paywalled content. Every document can be directly linked on the public dashboard. This layer determines narrative identity.

**Tier 1 — Institutional policy**

These are where macro narratives originate. Think tanks are downstream of this layer.

| Source | Document type | Volume | Retrieval |
|--------|--------------|--------|-----------|
| Fed Board — FOMC Statements | Policy decision + forward guidance | ~500–1,000 words, 8×/yr | federalreserve.gov structured endpoints |
| Fed Board — FOMC Minutes | Full deliberation record including dissenting views | 10,000–15,000 words, 8×/yr, 3-week lag | federalreserve.gov |
| Fed Board — Speeches | Narrative testing before policy crystallization; track speaker identity | 2,000–8,000 words, 50–100/yr | federalreserve.gov/news/speeches |
| Fed Board — Beige Book | 12 regional qualitative economic condition narratives + national summary; ingest each section separately | 15,000–25,000 words total, 8×/yr | federalreserve.gov |
| Fed Board — FEDS Notes | Board economists' fast analytical response; faster than working papers | 1,000–3,000 words, ~70/yr | federalreserve.gov/econres/feds |
| Fed Board — MPR, FSR | Monetary Policy Report (2×/yr); Financial Stability Report (2×/yr) | Long-form | federalreserve.gov |
| Regional Fed blogs | Fast institutional text; authoritative within days of major events | 500–2,000 words, multiple/week collectively | Individual RSS feeds (see list below) |
| IMF Blog | IMF's fast-response analytical layer; previews WEO/GFSR framing | 800–2,000 words, multiple/week | imf.org/en/Blogs RSS |
| IMF — WEO, GFSR | Formal flagship reports; international macro and financial stability | 2×/yr each | imf.org structured downloads |
| BIS Quarterly Review | Best source for banking-sector and financial stability narratives | 3–6 articles, 3,000–8,000 words each, 4×/yr | bis.org direct download |
| CEA Blog | Executive branch macro framing; distinct from Fed on labor/fiscal | 500–1,500 words, ~75/yr | whitehouse.gov/cea RSS |
| Treasury / OFR / FSOC | FSOC Annual Report; OFR working papers; Treasury crisis statements | Low volume, high signal | treasury.gov, financialresearch.gov, fsoc.gov |
| CBO | Economic and Budget Outlooks; fiscal narrative | ~50/yr | cbo.gov |
| Congressional testimony | Fed Chair, Treasury Secretary at Senate/House committees; primary narrative moments | ~40 key/yr | congress.gov, federalreserve.gov/testimony |

**Regional Fed blogs — ingest all of the following explicitly:**
- NY Fed Liberty Street Economics — `libertystreeteconomics.newyorkfed.org` — multiple posts/week; fastest institutional layer
- SF Fed Economic Letters and blog — `frbsf.org`
- Chicago Fed On the Economy — `chicagofed.org`
- Atlanta Fed macroblog — `frbatlanta.org`
- Dallas Fed Economics — `dallasfed.org`
- St. Louis Fed On the Economy — `stlouisfed.org`
- Cleveland Fed Economic Commentary — `clevelandfed.org`

**Note on Jackson Hole:** Jackson Hole symposium speeches are Fed Chair and governor speeches published on federalreserve.gov. They are captured by the Fed speeches ingestor. Do not implement a separate Jackson Hole ingestor — it creates duplicates. Confirm the Fed speeches ingestor scope includes these documents and remove any separate Jackson Hole source that exists in the codebase.

**Tier 2 — Academic-analytical**

| Source | Document type | Volume | Retrieval |
|--------|--------------|--------|-----------|
| VoxEU / CEPR | Academic economists writing fast accessible policy commentary; often frames narratives before press | 800–2,500 words, ~1,000 macro-relevant/yr | voxeu.org RSS (back to 2007) |
| Brookings Institution | High authority, fast response; Hutchins Center on Fiscal and Monetary Policy especially relevant | 500–5,000 words, ~500 macro-relevant/yr | brookings.edu RSS |
| PIIE (Peterson Institute) | World-class international macro; best free source for dollar, trade, and global monetary narratives | 500–3,000 words, ~300/yr | piie.com RSS |
| CFR (Council on Foreign Relations) | Geopolitical-financial narrative intersection; global macro policy | 500–3,000 words, ~200/yr | cfr.org RSS |

**Sources removed — archived, not deleted:**

| Source | Location | Reason |
|--------|----------|--------|
| AP News | `scripts/archive/` | Journalism layer replaced by Media Cloud Premium Press (Layer 1B, ADR-016) |
| MarketWatch | `scripts/archive/` | Same |
| GDELT | `scripts/archive/` | Superseded; no full text; quality issues |
| Common Crawl ingestor | `scripts/archive/` | Superseded |
| ProQuest export script | `scripts/archive/` | Superseded |
| arXiv | Remove from any active scripts immediately | Cut from scope: 2017-only coverage, low macro volume, not in spec |
| Jackson Hole (separate ingestor) | Remove from any active scripts immediately | Redundant: covered by Fed speeches ingestor |
| NBER | Removed entirely (ADR-017) | Bulk retrieval failed; live RSS also dropped — no new sources in Phase 6 beyond Tier 1/2 re-ingest + Media Cloud Premium |
| SSRN | Removed entirely (ADR-017) | Same as NBER |

---

### Layer 1B — Journalism Coverage via Media Cloud Premium Press (dynamics fitting only, no text embedding)

**(ADR-016, 2026-05-18: replaces the prior RavenPack-via-WRDS plan.)** Media Cloud's premium-press outlet collection — WSJ, Bloomberg, FT, Reuters, NYT, Barron's, Dow Jones Newswires, MarketWatch, AP Business, Bloomberg Businessweek, and similar — supplies daily story counts by keyword and entity, consistent from 2010 onward. Free, academically accessible, no subscription gate. Same Media Cloud API as Layer 2; the difference is the outlet collection scoped to in the query.

**What Layer 1B provides:** Daily and weekly article volume time series per narrative keyword/entity. No full text — we never embed Media Cloud content. Premium-press scope ensures the signal measures professional financial journalism propagation rather than open-web noise.

**What Layer 1B does NOT do:** Provide full text for embedding. Narrative identity is determined entirely by the institutional + academic text in Layer 1A. Media Cloud measures how widely a narrative has propagated into financial journalism after being characterized in analytical discourse.

**Role in dynamics fitting:** Layer 1B provides Signal A — the primary volume series for SIR/logistic parameter estimation. It is richer and more consistent than institutional corpus counts alone, especially for the 2010–2015 window when think tank digital presence was smaller. Concordance between Layer 1B dynamics (journalism propagation) and Layer 1A own-corpus dynamics (analytical community engagement) is itself a finding — it measures how quickly analytical framing propagates into financial journalism, a direct empirical test of Shiller's propagation framework.

| Source | Provides | Access |
|--------|---------|--------|
| Media Cloud API, premium-press outlet collection | Daily/weekly article count time series per keyword/entity across ~30 curated premium financial outlets, 2010–present | `MEDIACLOUD_API_KEY` in `.env` (free academic access) |

**Implementation:** `src/mnd/detection/mediacloud.py` (extends Layer 2 module). Query Media Cloud `/stories/count` endpoint scoped to the premium-press collection. Filter to macro-relevant keyword set (the canonical filter at `config/topic_filter_keywords.yaml`). Output weekly volume time series per narrative keyword to `data/dynamics/mediacloud_premium/`. Store entirely separately from the Layer 1A document pipeline — these are time series, not documents.

**Deprecated:** `src/mnd/ingestion/ravenpack.py` remains in the repo for reference but is NOT imported or invoked. Do not pass `WRDS_*` env vars; they are obsolete.

---

### Layer 2 — Detection via Media Cloud

Media Cloud provides story count time series by keyword/entity across thousands of outlets. No full text. Its sole function is detecting when a topic receives anomalous volume attention — firing a candidate narrative flag before institutional sources have characterized it in embeddable text.

**Detection → characterization sequence:**
- Day 0–3: Media Cloud volume spike detected (candidate flag raised)
- Day 3–14: Regional Fed blog and think tank documents arrive, get embedded, cluster begins forming
- Day 14–21: Formal Fed communications, IMF Blog engage with the narrative
- Week 3+: Media Cloud Premium volume confirms press-level propagation; cluster has sufficient volume for dynamics fitting

The lag between Media Cloud detection and institutional characterization is a measurable signal of narrative propagation speed — not a system weakness.

| Source | Provides | Access |
|--------|---------|--------|
| Media Cloud | Daily story counts by keyword/entity/outlet tier, 2010–present | mediacloud.org API — `MEDIACLOUD_API_KEY` in `.env` |

**Implementation:** `src/mnd/detection/mediacloud.py`. Output to `data/detection/mediacloud/`. Do not integrate into the embedding or clustering pipeline.

---

### Layer 3 — Validation Data

Not ingested as text. Used for: (1) exploratory outcome correlation — checking whether detected narrative dynamics co-move with real-world macro outcomes to establish face validity; (2) business cycle context labeling. Anchor narrative timing validation does not use this layer — it compares detected cluster emergence dates directly against `data/anchors/anchor_narratives.jsonl`.

| Source | Provides | Access | Role |
|--------|---------|--------|------|
| FRED | CPI, PCE, unemployment, yield curve, breakeven inflation, VIX, credit spreads | `fredapi`, free; `FRED_API_KEY` in `.env` | Primary outcome correlation series |
| EPU (Baker-Bloom-Davis) | Monthly news-based economic policy uncertainty index, 1985–present | policyuncertainty.com, free direct download | Strongest face-validity benchmark — EPU is itself built from newspaper text coverage of uncertainty, directly comparable to this system's output; narrative emergence events should co-move with EPU spikes |
| NBER Business Cycle Dating | Official U.S. recession start/end dates | nber.org, public | Cycle context labels; not for correlation |
| University of Michigan consumer sentiment | Monthly inflation expectations and consumer sentiment | FRED | Inflation narrative validation specifically |

**EPU replaces JLN:** The Jurado-Ludvigson-Ng index has been removed. JLN measures forecast error variance — an indirect signal requiring WRDS MFS access. EPU is constructed from the same kind of text-based discourse this project analyzes, is freely downloadable, and is the stronger benchmark for this specific use case. Remove any `WRDS_MFS_*` env vars related to JLN.

---

## 5. System Architecture — 7 Stages

Each stage produces a checkpointed artifact. Downstream stages consume the prior checkpoint. Partial completion still produces useful outputs. Failures in one stage do not require redoing upstream work.

```
Stage 1: Ingestion
Stage 2: Filtering and Deduplication
Stage 3: Embedding
Stage 4: Clustering
Stage 5: Dynamics Fitting
Stage 6: Stage Classification
Stage 7: Dashboard
```

---

### Stage 1: Ingestion

Pull documents from all Layer 1A sources. Each ingestor outputs documents with the following standard schema:

```json
{
  "doc_id":           "unique identifier",
  "source":           "ny_fed_liberty_street",
  "source_tier":      "institutional_policy",
  "doc_type":         "blog_post | speech | statement | minutes | report | brief | testimony",
  "title":            "...",
  "body_text":        "...",
  "publication_date": "YYYY-MM-DD",
  "author":           "...",
  "url":              "...",
  "tags":             ["..."]
}
```

**Timestamp rule:** Use publication/release date, not meeting or event date. FOMC minutes timestamp = release date (3 weeks after meeting), not the meeting date. The system measures when ideas enter public discourse.

Run Layer 1B Media Cloud Premium ingestion separately via `src/mnd/detection/mediacloud.py`. Output goes to `data/dynamics/mediacloud_premium/` as time series — do not mix with document records from Layer 1A.

---

### Stage 2: Filtering and Deduplication

No topic filter needed — all Layer 1A sources are macro-relevant by construction. Two operations only:

1. **Near-duplicate removal:** MinHash-based detection within rolling 48-hour windows. Removes wire redistributions and minor edits. Retain one canonical version per duplicate cluster.
2. **Date range filter:** Retain only documents with `publication_date` between 2010-01-01 and present.

---

### Stage 3: Embedding

**Two-model strategy (resolved per ADR-011, 2026-05-11):**

- **Primary (production): `Qwen/Qwen3-Embedding-0.6B`** — 1024-dim, 32,768-token context,
  instruction-aware, Apache 2.0. Long context is essential for the corpus:
  FOMC minutes 10–15k words, BIS QR 3–8k, Jackson Hole 8–15k, VoxEU 800–2,500.
  Ranks at the top of MTEB clustering benchmarks (early 2025).
  - On RCC: `max_seq_len=1024`, `batch_size=8`, fp16 (V100 16 GB OOM-safe, ADR-013).
    The 600-BPE-token chunker output fits with 1.7× headroom.
  - On Apple Silicon (MPS): set `MND_MAX_SEQ_LEN=512` in `.env` to avoid OOM on the
    attention matrix (ADR-006).
  - Upgrade path: `Qwen/Qwen3-Embedding-4B` if RCC capacity allows; identical interface.

- **Comparator (look-ahead sensitivity check only): `all-mpnet-base-v2`** —
  768-dim, 384-token native context, ~2020–2021 training cutoff. Not used for
  production clustering. Sole role: run on the 10 anchor narrative sub-corpora
  (±3 months around each reference date), compute NMI and pairwise silhouette
  separately for pre-2021 and post-2021 windows, report Δ_NMI(post − pre) for
  each model.
  - **Kill criterion:** if Qwen3's Δ_NMI exceeds 0.15 AND mpnet's does not show
    the same pattern → flag significant look-ahead bias and add caveat to the
    pre-registration and methodology section. If both models track, look-ahead
    is bounded by vocabulary stability (the expected result for institutional register).

The honest framing: both models have look-ahead exposure on some of the historical
corpus. Qwen3 has more exposure but also far superior context and representational
quality. The right response is to measure the exposure, not to assume the weaker
model is unbiased. The two-model design makes the look-ahead argument formal.

**Embedding procedure:**
- Truncate input to: headline + first 600 tokens of body text (chunk-level)
- Documents over 2,000 words: split into overlapping 600-token chunks with
  100-token overlap; embed each chunk separately (BPE tokens, tiktoken
  cl100k_base; `src/mnd/processing/chunker.py`)
- Each chunk carries full parent document metadata; chunk-to-document mapping
  preserved in `data/processed/chunks.parquet`
- For dynamics counting, count by document (not by chunk) — see
  `chunker.merge_chunk_embeddings`
- Run on RCC GPU partition (`scripts/rcc/embed_rcc.sh`); the
  `submit_full_pipeline.sh` chain runs primary and comparator in parallel by
  default (`COMPARATOR=1`)

---

### Stage 4: Clustering

BERTopic with dynamic topic modeling.

**Locked parameters — do not change without a new ADR:**
```yaml
umap_n_neighbors: 15
umap_min_dist: 0.1
umap_n_components: 5
umap_metric: cosine
hdbscan_min_cluster_size: 20        # default; sensitivity sweep {10, 20, 40}
hdbscan_min_samples: 5
hdbscan_cluster_selection_method: eom
```

**Three granularity levels:**
- Fine: 200+ clusters
- Medium: 40–80 clusters — primary analysis unit; a "narrative" is operationally a medium-granularity cluster
- Coarse: 10–20 clusters

**Bootstrap stability evaluation:** 20 replicates with deterministic seeds. Report NMI and ARI across all pairs for each granularity level.

**Kill criterion:** NMI < 0.40 across all parameter settings → stop, investigate, do not proceed.

**Post-clustering diagnostics (run after clustering, one-time, do not feed back into clustering):**
- *Source-type contamination check:* For each cluster, groupby `source_tier`. Flag clusters > 90% one source type for manual review — potential register-based rather than semantic clustering.
- *Look-ahead sensitivity check:* Compute NMI separately for pre-2021 and post-2021 sub-corpora. If clusters are dramatically cleaner post-2021, document as evidence of significant look-ahead bias.

---

### Stage 5: Dynamics Fitting

Two volume signals feed this stage and are kept operationally separate.

**Signal A — Media Cloud Premium press volume (primary)**
Weekly article counts from the ~30-outlet premium press whitelist. Primary series for SIR/logistic parameter estimation. Consistent, outlet-normalized, full 2010–present window. Stored at `data/dynamics/mediacloud_premium/`.

**Signal B — Institutional corpus document counts (secondary)**
Per-cluster document counts from Layer 1A. Count by document, not by chunk. Measures analytical-institutional community engagement. Stored at `data/dynamics/institutional/`.

**Concordance between Signal A and Signal B is a finding.** Concordant dynamics (similar R₀ and peak timing) indicates rapid propagation from analytical framing to journalism. Divergence — institutional engagement preceding press peak — is a measurable lag in narrative transmission speed and a direct empirical result for the Shiller framework.

**Fitting procedure for each narrative cluster:**

1. Extract Signal B time series (Layer 1A document counts per day)
2. Extract Signal A time series (Media Cloud Premium weekly volume for matched canonical-filter keyword set)
3. Apply 7-day centered moving average smoothing to both series (bump to 21-day if noisy — this is the only parameter to adjust before escalating)
4. Apply **stratified smoothing** on Signal B — smooth institutional and think-tank documents separately to prevent quarterly BIS or IMF report releases from spiking the series
5. Apply **calendar annotation** — flag FOMC meeting dates, BLS release dates, and major known macro events on the weekly series
6. Fit four parametric models in parallel **on Signal A** (primary): SIR, logistic, Gompertz, exponential
7. Fit logistic model **on Signal B** (secondary) for comparison
8. Use Bayesian inference with weakly-informative priors (PyMC) — full posterior distributions over parameters, not point estimates
9. **Volume normalization (Signal A):** Express weekly Media Cloud Premium counts as fraction of total Media Cloud Premium articles that week. Makes R₀ comparable across years; absorbs outlet coverage expansion effects.

**Two-stage fitting threshold:** Apply parametric models only when a cluster exceeds **3 articles/week averaged over 4 consecutive weeks AND 50 cumulative articles** in Signal A. Below threshold: descriptive stats only (first appearance, cumulative count, most recent document title). Label "pre-fitting" in dashboard. Do not force a fit on thin data.

---

### Stage 6: Stage Classification

Classify each narrative cluster into one of five life-cycle stages based on its fitted Signal A curve:

| Stage | Criteria |
|-------|----------|
| Pre-emergence | < 50 cumulative articles in Signal A; R₀ poorly identified |
| Early-spread | R₀ > 1.0; currently in growth phase; peak day not yet reached |
| Peak | At or near maximum daily volume; growth rate near zero |
| Decay | Post-peak; declining article volume |
| Dormant | Very low volume; R₀ < 1; narrative effectively concluded |

Threshold values are pre-specified in `config.yaml`. Do not modify without a new ADR.

---

### Stage 7: Dashboard

Public web tool. Reads pre-computed static artifacts only — no live computation at user request time. Two primary views:

**View 1 — Life-Cycle Viewer:** Select a narrative → growth curve with fitted model overlaid, R₀ estimate with credible interval, current life-cycle stage, representative document titles from key moments, links to original source URLs.

**View 2 — Emerging Narratives Panel:**
- *Currently emerging:* Narratives crossing from pre-emergence into early-spread within the past 7–30 days; R₀ estimate, current volume, sample titles
- *Historical analogs:* Top 3–5 historical narratives with most similar early-stage Signal A trajectories
- *Aggregate state:* Number of narratives per stage, dominant clusters, current discourse landscape

**Stretch — Narrative Map:** 2D UMAP projection with cluster centroids labeled, zoom and click. Cut this if time-constrained.

**Onboarding:** Persistent "what is this?" page with plain-language explanation and a worked historical example. Tooltips on R₀, stage labels, and technical terms.

**Live update architecture:** Weekly cron job (RCC or small VPS). Pulls past week's documents from all Layer 1A sources. Embeds, assigns to existing clusters or flags candidate new clusters. Refits parameters on changed clusters. Writes static JSON/HTML artifacts. Frontend (Hugging Face Spaces or Vercel free tier) reads static artifacts only. If a weekly update fails, display last-good state with prominent "last updated" timestamp.

---

## 6. Current Project Status

### Complete
- **Phase 1 — Pilot:** Bootstrap NMI passes kill criterion. Three-narrative anchor detection confirmed. Do not rerun or modify pilot code.
- **Phase 2 — Data Pipeline:** Full historical ingestion (2010–present) ran on RCC. Ingested corpus includes institutional sources, AP News (Wayback CDX), and MarketWatch (Wayback CDX).

### In Progress
- **Phase 3 — Embedding, Clustering, Dynamics:** Running on RCC. SLURM embedding jobs had dependency resolution issues at last check. Clustering and dynamics fitting not yet confirmed complete.

### Known Issues to Fix Before Proceeding

**Issue 1 — arXiv is active in `ingest_institutional_rcc.sh`:**
arXiv was cut from scope. Remove it from the Tier 2 sources list in the ingest script and from any source configuration files (`whitelist.yaml`, etc.). arXiv has 2017-only coverage, low macro volume, and is not in this spec.

**Issue 2 — Jackson Hole papers listed as a separate source:**
Remove any separate Jackson Hole ingestor. These speeches are Fed Chair and governor speeches on federalreserve.gov, already captured by the Fed speeches ingestor. A separate ingestor creates duplicates. Confirm Fed speeches ingestor covers them, then remove the redundant entry from all scripts and config.

**Issue 3 — AP News and MarketWatch in the processed corpus:**
These were ingested in Phase 2 but have since been removed from scope. Before embedding (if not yet run): write `scripts/filter_corpus_pre_embed.py` to filter `data/processed/` excluding documents where `source` is `ap_news` or `marketwatch`, output to `data/processed/corpus_for_embedding.jsonl`, report counts before/after. If embedding is already complete: filter by dropping those rows from the embedding matrix before clustering.

**Issue 4 — Embedding model decision:** RESOLVED per ADR-011 (2026-05-11).
Qwen3-Embedding-0.6B is the primary production model; mpnet is the comparator
for the formalized look-ahead sensitivity check. See Stage 3 above for the
full procedure and ADR-013 for the V100 OOM-driven `max_seq_len=1024` /
`batch_size=8` adjustments. No further evaluation needed before the historical
RCC run.

---

## 7. Immediate Tasks for Claude Code

**First action — determine actual Phase 3 state:**

```bash
squeue -u ehgarver
sacct -u ehgarver --starttime=2026-05-01 --format=JobID,JobName,State,Elapsed
ls -lh /scratch/midway3/ehgarver/data/embeddings/ 2>/dev/null
ls -lh /scratch/midway3/ehgarver/data/clusters/ 2>/dev/null
```

Report what exists. Then proceed in this order:

1. Fix Issue 1: remove arXiv from `ingest_institutional_rcc.sh` and all config
2. Fix Issue 2: remove Jackson Hole separate ingestor; confirm Fed speeches covers it
3. Fix Issue 3: filter AP News and MarketWatch from corpus (pre- or post-embed as appropriate)
4. Fix Issue 4: make embedding model decision; create ADR if changing
5. Add `src/mnd/detection/mediacloud.py` — new, does not exist; Media Cloud detection layer
6. ~~Confirm `src/mnd/ingestion/ravenpack.py`~~ DEPRECATED (ADR-016). Layer 1B is sourced from Media Cloud Premium via `src/mnd/detection/mediacloud.py`; output goes to `data/dynamics/mediacloud_premium/` as time series only.
7. Implement EPU validation data pull from policyuncertainty.com; remove any JLN/WRDS_MFS references
8. Remove env vars: `PROQUEST_DATASET_ID`, `NEWS_API_KEY`, `WRDS_*` (entire family — RavenPack via WRDS no longer used)
9. Commit and push all changes; confirm remote is up to date

---

## 8. Remaining Phases

### Phase 4 — Validation

Do not begin until Phase 3 NMI and ARI results are confirmed and pass kill criteria.

1. **Pre-registration first:** Commit `prereg/PREREGISTRATION.md` to a public timestamp (GitHub or OSF) before examining any outcome data. Must specify all hypotheses, variables, statistical tests, decision criteria before any FRED or EPU data is correlated against narrative clusters.

2. **Anchor narrative recovery:** System must recover all 10 anchor narratives within 14-day tolerance (Section 10).

3. **Fizzled-narrative validation:** For each anchor, validate that contemporaneous narratives that did not crystallize receive appropriately different stage classifications.

4. **Sensitivity analysis:** Three pre-specified parameter settings (strict: `min_cluster_size=10`, default: `20`, permissive: `40`). Core conclusions must hold across all three.

5. **Exploratory predictive analysis (compressible):** Granger causality testing in both directions; Benjamini-Hochberg FDR correction across all reported hypotheses. Null results reported honestly — not a project killer.

**Kill criteria for Phase 4:**
- Fewer than 7/10 anchors recovered within 14-day tolerance → debug; if persistent, shift to novelty-velocity framework
- Median R² < 0.30 OR R₀ posterior CIs > 2 units across validation narratives → drop SIR; fall back to logistic or non-parametric curve features

**Out-of-sample discipline:** Training data 2010–2019. Held-out validation 2020–present. Held-out period not examined until final analysis. All hyperparameters locked before held-out evaluation.

### Phase 5 — Dashboard Build

1. Streamlit (MVP) or React single-page app
2. Static cached artifacts from analysis pipeline (JSON cluster data, fitted parameters, stage classifications, document titles and URLs)
3. Implement View 1 (Life-Cycle Viewer) and View 2 (Emerging Narratives Panel)
4. Onboarding page with worked historical example
5. Deploy to Hugging Face Spaces (free tier, public URL, no authentication)

### Phase 6 — Live Updating

Weekly cron job. Pulls past week's documents from all active Layer 1A sources (Tier 1 + Tier 2 institutional/academic). Also refreshes Layer 1B Media Cloud Premium Press volume series. Does NOT activate NBER, SSRN, or any other source not in the historical corpus (ADR-017). Embeds new documents. Assigns to existing clusters or flags candidate new clusters. Refits parameters on changed clusters. Writes static artifacts. Failure handling: display last-good state with "last updated" timestamp.

### Phase 7 — Writeup and Reproducibility

1. GitHub: pinned dependencies (`requirements.txt`), clear README, replication instructions, pre-registration document, anchor narrative ground truth as CSV/JSONL
2. Short technical report: 5–8 pages covering methodology and findings
3. Stretch: 12–15 page workshop-paper quality writeup for ACL Economics and NLP or NeurIPS ML for Finance workshop

---

## 9. Locked Parameters

**Do not change any of these without creating a new ADR in `docs/architecture_decisions.md`.**

```yaml
# Embedding (ADR-011; ADR-013 for max_seq_len / batch_size)
embedding_primary_model:    Qwen/Qwen3-Embedding-0.6B
embedding_primary_max_seq_len: 1024       # RCC V100 16GB OOM-safe; 512 on MPS via MND_MAX_SEQ_LEN
embedding_primary_batch_size: 8           # V100 OOM-safe (was 32)
embedding_comparator_model: sentence-transformers/all-mpnet-base-v2
embedding_comparator_max_seq_len: 384     # mpnet native max
article_truncation_tokens: 600
chunk_size_tokens: 600
chunk_overlap_tokens: 100
chunk_threshold_words: 2000

# Clustering
umap_n_neighbors: 15
umap_min_dist: 0.1
umap_n_components: 5
umap_metric: cosine
hdbscan_min_cluster_size: 20              # default; sensitivity sweep {10, 20, 40}
hdbscan_min_samples: 5
hdbscan_cluster_selection_method: eom

# Dynamics
smoothing_window_days: 7                  # centered MA; only adjustment to try before escalating is bumping to 21
bootstrap_replicates: 20
anchor_tolerance_days: 14
pre_emergence_threshold_articles: 50
early_spread_r0_threshold: 1.0
fitting_threshold_articles_per_week: 3    # Signal A, over 4 consecutive weeks
fitting_threshold_cumulative: 50          # Signal A

# Validation split
train_cutoff: 2019-12-31
holdout_start: 2020-01-01

# Reproducibility
random_seed: pinned in config.yaml        # specific values there
```

---

## 10. Anchor Narratives — FINAL (10 narratives)

FTX and GameStop were removed (not macro-scoped). Taper tantrum and China devaluation added to cover the 2010–2015 window.

| # | Narrative | Reference Date | Why It Anchors |
|---|-----------|---------------|----------------|
| 1 | SVB collapse | 2023-03-09 | Entity-rich, sharp emergence, well-documented |
| 2 | COVID market crash | 2020-02-24 | Largest single-narrative event in window |
| 3 | Brexit aftermath | 2016-06-24 | Long-tail narrative with clear ignition |
| 4 | Transitory inflation debate | 2021-Q2 | Slower, diffuse; well-documented Fed language evolution |
| 5 | Credit Suisse stress | 2023-03-15 | Adjacent to SVB; tests cluster differentiation |
| 6 | Regional banking contagion | 2023-03-13 | Tests narrative branching from anchor events |
| 7 | 2022 inflation peak narrative | 2022-Q2/Q3 | Multi-month evolving narrative |
| 8 | Soft landing emergence | 2023-Q3/Q4 | Slow emergence; uncontested timing |
| 9 | 2013 taper tantrum | 2013-05-22 | Bernanke Senate testimony; tests 2010–2015 coverage |
| 10 | 2015 China devaluation scare | 2015-08-11 | PBOC devaluation; global contagion framing |

---

## 11. Kill Criteria

Pre-committed thresholds. If hit, stop and respond as specified — do not continue.

| Criterion | Threshold | Check Point | Response if Hit |
|-----------|-----------|-------------|-----------------|
| Cluster stability | Bootstrap NMI < 0.40 across all parameter settings | End of Phase 3 | Investigate; if unsalvageable, narrow to inflation-only fallback scope (2018–present) |
| Anchor recovery | Fewer than 7/10 anchors within 14-day tolerance | End of Phase 4 | Debug; if persistent, shift to novelty-velocity framework |
| Dynamics fit quality | Median R² < 0.30 OR R₀ CIs > 2 units across validation narratives | End of Phase 4 | Drop SIR; fall back to logistic or non-parametric curve features |
| Predictive null | No associations survive FDR correction | Phase 4 | Not a killer — report null honestly |
| Live update reliability | > 25% of weekly updates fail | Phase 6 month 1 | Degrade to monthly; make "last updated" prominent |
| Time budget | MVP not complete by month 3 | Mid-project | Cut stretch downward; preserve MVP above all else |

**Fallback scope:** If multiple kill criteria trigger stress, narrow to inflation discourse only, 2018–present. Corpus halves, semantic homogeneity increases, look-ahead window shortens, CPI/PCE/EPU validation becomes cleaner. Methodology, dashboard, and tooling all transfer unchanged.

---

## 12. Infrastructure

**Compute:** UChicago RCC Midway3
- Account: `pi-dachxiu` — use conservatively; do not exhaust allocation
- Scratch directory: `/scratch/midway3/ehgarver/` — all data here; never write to PI's project folder
- GPU partition for embedding; `caslake` (CPU) for clustering
- SLURM scripts in `scripts/rcc/`

**Environment variables (`.env`):**
```
FRED_API_KEY=...
WRDS_USERNAME=...
WRDS_PASSWORD=...
MEDIACLOUD_API_KEY=...
```

**Remove — no longer needed:**
```
PROQUEST_DATASET_ID
NEWS_API_KEY
WRDS_MFS_*        (JLN indices replaced by EPU)
```

**Data paths:**
```
/scratch/midway3/ehgarver/data/raw/                    # raw ingested documents
/scratch/midway3/ehgarver/data/processed/              # cleaned, filtered documents
/scratch/midway3/ehgarver/data/embeddings/             # embedding vectors + chunk-doc mapping
/scratch/midway3/ehgarver/data/clusters/               # BERTopic output, all granularity levels
/scratch/midway3/ehgarver/data/dynamics/mediacloud_premium/     # Signal A — Media Cloud Premium time series
/scratch/midway3/ehgarver/data/dynamics/institutional/ # Signal B — corpus document counts
data/detection/mediacloud/                             # Media Cloud detection signals (local)
data/raw/validation/                                   # FRED, EPU, NBER recession dates (local)
data/anchors/anchor_narratives.jsonl                   # anchor narrative ground truth
```

**Commit and push discipline:** Every session ends with a commit and push to origin. Confirm remote is up to date before ending any Claude Code session.

**Stale-checkpoint pitfall (operational, learned 2026-05-17/18):**
`InstitutionalIngestor` writes per-sub-ingestor completion state to
`data/raw/articles/.institutional_checkpoint.json`. On startup it reads that
file and SKIPS any sub-ingestor marked `"status": "completed"`. The default
archive mode of `submit_full_pipeline.sh` does NOT touch `data/raw/`, so a
checkpoint from a smaller-window prior run (e.g. a 2024-only dry-run with
Fed=142 articles) silently causes the new run to skip Fed even though the
new window is 2010-2026. Result: incomplete corpus, no error.

**Rule:** any time the date window changes, or after a dry-run, re-submit
with `NUKE_RAW=1 bash scripts/rcc/submit_full_pipeline.sh`. That triggers
the codepath in the script that archives `data/raw/` (including the
checkpoint) along with `data/processed/`. Nothing is deleted under the
default `NUKE_PRIOR=0`; everything moves to a timestamped
`_archived_<TS>/` folder under `/scratch/midway3/ehgarver/data/`.

---

## 13. Statistical Reporting Standards

- All quantitative claims report 95% bootstrap confidence intervals
- All multiple-comparison contexts report both raw p-values and Benjamini-Hochberg corrected significance
- Any predictive analysis additionally reports Deflated Sharpe Ratio if portfolio-style framings are used
- Null results reported honestly — a null exploratory finding is still a valid finding

---

*Document version: 2026-05-17 rev4. Embedding section (§3 Stage 3, §6 Issue 4, §9) updated to reflect the resolved ADR-011 decision: Qwen3-Embedding-0.6B is the primary production model and all-mpnet-base-v2 is the comparator for the formalized look-ahead sensitivity check. ADR-013 V100-OOM adjustments (max_seq_len=1024, batch_size=8) and ADR-014 IMF Coveo+curl_cffi retrieval path noted in passing. All other rev3 architecture stands.*

*Rev3 history (2026-05-11): Full rewrite. Key changes from prior versions: arXiv removed; Jackson Hole removed as separate source (covered by Fed speeches); RavenPack restructured as Layer 1B journalism supplement providing Signal A for dynamics fitting; Media Cloud is standalone Layer 2 detection; JLN replaced by EPU in Layer 3; Stage 5 rewritten for dual-signal dynamics approach; known issues section added covering all immediate fixes. The original project plan PDF remains valid for theoretical background; this document governs all implementation decisions.*
