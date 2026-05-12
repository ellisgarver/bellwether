# Macro Narrative Dynamics — Full Project Specification
**For Claude Code. This document supersedes all prior CLAUDE.md content, architecture decisions, and source specifications. Read this entirely before touching any code.**

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
- **Logistic growth** — f(t) = L / (1 + e^(-k(t-t₀))), robust fallback
- **Gompertz growth** — asymmetric peak, common in diffusion modeling
- **Simple exponential** — baseline for early-stage narratives

If SIR fits poorly across the validation set, fall back to logistic growth or non-parametric raw curve features (peak velocity, time-to-peak, decay slope). Logistic is the MVP fallback and is always fit regardless.

---

## 4. Data Source Architecture — FINAL

**This replaces all prior corpus architecture decisions. The AP News and MarketWatch journalism tier has been cut as direct text sources. The GDELT and Common Crawl sources remain archived. NBER and SSRN are removed from the historical ingestion pipeline (they remain available for Phase 6 live updates only, per prior decision).**

The corpus is built on three functionally distinct layers. Each layer maps directly onto a phase of Shiller's narrative propagation framework: narratives are characterized in analytical institutional discourse (Layer 1 text), propagate into financial journalism (Layer 1 RavenPack), and their emergence is detected via broad volume signals before institutional characterization begins (Layer 2). These layers are kept operationally separate — RavenPack contributes to dynamics fitting but not to text embedding; Media Cloud contributes to detection only.

### Layer 1: Corpus (semantic text + journalism coverage)

Layer 1 has two sub-components with different roles. **1A** provides the text that gets embedded and clustered — this is where narrative identity is determined. **1B** provides structured premium press coverage via RavenPack that supplements the dynamics fitting with a journalism propagation signal — this does NOT feed text embedding.

#### 1A — Semantic Text Sources (embedding and clustering)

All sources are free, open access, and programmatically retrievable. No paywalled content. Every document in this layer can be directly linked on the public dashboard.

**Tier 1 — Institutional policy (primary narrative sources)**

These are where macro narratives originate. Think tanks and analytical outlets are downstream of this layer.

| Source | What it provides | Retrieval | Notes |
|--------|-----------------|-----------|-------|
| Fed Board — FOMC Statements | ~500–1,000 words, 8×/yr; policy decision + forward guidance language | federalreserve.gov structured endpoints | Highest-authority narrative anchors; every word deliberate |
| Fed Board — FOMC Minutes | 10,000–15,000 words, 8×/yr, 3-week lag | federalreserve.gov | Records narrative debate; "several participants noted..."; most valuable single document type |
| Fed Board — Speeches | 2,000–8,000 words, 50–100/yr | federalreserve.gov/news/speeches | Narrative testing before crystallization in statements; track speaker identity |
| Fed Board — Beige Book | 15,000–25,000 words, 8×/yr; 12 regional sections | federalreserve.gov | Regional narrative texture; qualitative economic conditions; ingest national summary + each region separately |
| Fed Board — FEDS Notes | 1,000–3,000 words, ~70/yr | federalreserve.gov/econres/feds | Board economists' fast-response analytical layer; faster than working papers; public domain |
| Fed Board — MPR, FSR | Monetary Policy Report (2×/yr), Financial Stability Report (2×/yr) | federalreserve.gov | Formal narrative crystallization documents |
| Regional Fed blogs | 500–2,000 words, multiple/week collectively | Individual RSS feeds | Fastest embeddable institutional text; authoritative within days of events |
| IMF Blog | 800–2,000 words, multiple/week | imf.org/en/Blogs RSS | IMF's fast-response layer; international macro framing; previews WEO/GFSR language |
| IMF — WEO, GFSR | 2×/yr each; formal flagship reports | imf.org structured downloads | Formal international institutional characterization |
| BIS Quarterly Review | 3–6 articles, 3,000–8,000 words each, 4×/yr | bis.org direct download | Best source for banking-sector and financial stability narratives; highly rigorous |
| CEA Blog | 500–1,500 words, ~75/yr | whitehouse.gov/cea RSS | Executive branch macro framing; distinct from Fed framing on labor/fiscal narratives |
| Treasury / OFR / FSOC | FSOC Annual Report, OFR working papers, Treasury statements | treasury.gov, financialresearch.gov, fsoc.gov | Financial stability narrative; FSOC Annual Report is primary systemic risk characterization |
| CBO | Economic and Budget Outlooks, supplemental reports | cbo.gov | Fiscal policy narrative; narrow scope but clean signal |

**Regional Fed blogs to ingest explicitly:**
- NY Fed Liberty Street Economics — `libertystreeteconomics.newyorkfed.org` — multiple posts/week, fastest
- SF Fed Economic Letters and blog — `frbsf.org`
- Chicago Fed On the Economy — `chicagofed.org`
- Atlanta Fed macroblog — `frbatlanta.org`
- Dallas Fed Economics — `dallasfed.org`
- St. Louis Fed On the Economy — `stlouisfed.org`
- Cleveland Fed Economic Commentary — `clevelandfed.org`

**Tier 2 — Academic-analytical (fast academic framing)**

| Source | What it provides | Retrieval | Notes |
|--------|-----------------|-----------|-------|
| VoxEU / CEPR | 800–2,500 words, ~1,000 macro-relevant/yr | voxeu.org RSS (back to 2007) | Academic economists writing accessible policy commentary; fastest academic layer; often frames narratives before press |
| Brookings Institution | 500–5,000 words, ~500 macro-relevant/yr | brookings.edu RSS | High authority, fast response; Hutchins Center on Fiscal and Monetary Policy is especially relevant |
| PIIE (Peterson Institute) | 500–3,000 words, ~300/yr | piie.com RSS | World-class international macro; best free source for dollar dynamics, trade, and global monetary narratives |
| CFR (Council on Foreign Relations) | 500–3,000 words, ~200/yr | cfr.org RSS | Geopolitical-financial narrative intersection; global macro policy |

**Sources explicitly excluded from historical ingestion (archived, not deleted):**
- AP News — removed; replaced by RavenPack as the journalism coverage signal (see 1B)
- MarketWatch — removed; same reason
- GDELT — archived at `scripts/archive/`; superseded
- Common Crawl ingestor — archived; superseded
- ProQuest export script — archived; superseded
- NBER — historical bulk retrieval failed (JavaScript-rendered, bot-protected); removed from historical corpus; RSS feed remains for Phase 6 live updates only
- SSRN — same as NBER; live updates only

#### 1B — Journalism Supplement via RavenPack (dynamics fitting only, no text embedding)

RavenPack provides structured article-level metadata and volume time series from ~30 premium financial outlets (WSJ, Bloomberg, FT, Reuters, and others) consistently from 2010 to present. Access is via WRDS academic subscription — no paywall scraping, no Wayback CDX patching, no coverage inconsistency.

**What RavenPack contributes:** Article volume time series per outlet cluster, event category tags (macro, monetary policy, recession, inflation, etc.), relevance scores, and sentiment scores. It does NOT provide full text for embedding.

**What RavenPack does NOT do:** Feed the semantic clustering pipeline. Narrative *identity* is determined entirely by the institutional text in 1A. RavenPack measures how widely a narrative has propagated into financial journalism after it has been characterized in analytical discourse.

**Role in dynamics fitting:** RavenPack provides the primary volume series for SIR/logistic parameter estimation. The institutional corpus document counts (from 1A) provide a secondary, analytical-community-specific dynamics signal. Fitting on RavenPack press volume gives broader, more consistent time series than institutional counts alone, especially for the 2010–2015 window when think tank digital presence was smaller. Concordance between institutional corpus dynamics and RavenPack dynamics is itself a finding — it measures how quickly analytical framing propagates into financial journalism.

| Source | What it provides | Access | Notes |
|--------|-----------------|--------|-------|
| RavenPack RPA 1.0 Global Macro, Dow Jones Edition | Weekly article volume time series, event tags, relevance/sentiment scores per outlet cluster, 2010–present | WRDS (`WRDS_USERNAME`, `WRDS_PASSWORD`) | Research-standard; covers premium press without paywalls; do not use for text embedding |

**Implementation note:** RavenPack data goes to `data/dynamics/ravenpack/` — separate from the semantic corpus pipeline. The ingestor (`src/mnd/ingestion/ravenpack.py`) queries via WRDS PostgreSQL or Python API, filters to macro-relevant event categories, and outputs weekly volume time series per outlet cluster. Store separately; do not mix with document metadata from 1A.

---

### Layer 2: Detection (narrative emergence signaling)

Media Cloud provides story count time series by keyword/entity across thousands of outlets. It does not provide text. Its sole role is to detect when a topic is receiving anomalous volume attention — firing a candidate narrative flag before institutional sources have characterized it in embeddable text. This is the earliest signal in the pipeline.

**What Media Cloud contributes:** Daily story counts per keyword/topic query, outlet-tier breakdown (prestige national vs. regional vs. trade press). When volume for a topic cluster exceeds a threshold or shows anomalous growth relative to baseline, flag as candidate narrative. This creates a provisional detection event that gets enriched as 1A institutional documents arrive.

**The detection → characterization sequence:** Media Cloud fires (day 0–3) → think tank and regional Fed blog documents begin arriving and get embedded into a cluster (day 3–14) → cluster gains sufficient volume for dynamics fitting → RavenPack confirms press-level propagation. The lag between Media Cloud detection and institutional characterization is itself a measurable signal of narrative propagation speed.

| Source | What it provides | Access | Notes |
|--------|-----------------|--------|-------|
| Media Cloud | Daily story count time series by keyword/entity/outlet tier, 2010–present | mediacloud.org API; `MEDIACLOUD_API_KEY` in `.env` | Detection only; no text; do not embed |

### Layer 3: Validation Data

Not ingested as text. Used for two distinct purposes: (1) exploratory outcome correlation — checking whether detected narrative dynamics co-move meaningfully with real-world macro outcomes to establish face validity; (2) business cycle context labeling — marking narrative life-cycles as occurring during expansion or recession. Anchor narrative timing validation does not use this layer at all — that check compares detected cluster emergence dates directly against documented reference dates in `anchor_narratives.jsonl`.

| Source | Provides | Access | Role |
|--------|---------|--------|------|
| FRED | CPI, PCE, unemployment, yield curve, breakeven inflation, VIX, credit spreads | `fredapi`, free; `FRED_API_KEY` in `.env` | Primary outcome correlation series |
| EPU (Baker-Bloom-Davis Economic Policy Uncertainty) | Monthly news-based economic policy uncertainty index, 1985–present | policyuncertainty.com, free direct download | Strongest face-validity benchmark — EPU is itself constructed from newspaper text coverage of uncertainty, directly comparable to this system's narrative detection; narrative emergence events should co-move with EPU spikes |
| NBER Business Cycle Dating | Official U.S. recession start/end dates | nber.org, public | Cycle context labels on narrative life-cycles; not for correlation |
| University of Michigan consumer sentiment | Monthly inflation expectations and consumer sentiment | FRED | Inflation narrative validation specifically — check whether inflation narrative clusters co-move with survey-based expectations |

**Note on EPU replacing JLN:** The Jurado-Ludvigson-Ng index (previously listed) measures forecast error variance — an indirect signal. EPU is constructed from the same kind of discourse this project analyzes, making it the strongest available external benchmark. Concordance between system-detected narrative emergence and EPU spikes is meaningful evidence the detection is capturing economically real signal rather than statistical noise.

---

## 5. System Architecture — 7 Stages

Each stage produces a checkpointed artifact. Downstream stages consume the prior checkpoint. Partial completion produces useful outputs. Failures in one stage do not require redoing upstream work.

```
Stage 1: Ingestion
Stage 2: Filtering and Deduplication
Stage 3: Embedding
Stage 4: Clustering
Stage 5: Dynamics Fitting
Stage 6: Stage Classification
Stage 7: Dashboard
```

### Stage 1: Ingestion

Pull documents from all Tier 1 and Tier 2 sources above. Each ingestor outputs documents with the following standard fields:

```json
{
  "doc_id": "unique identifier",
  "source": "ny_fed_liberty_street",
  "source_tier": "institutional_policy",
  "doc_type": "blog_post | speech | statement | minutes | report | brief",
  "title": "...",
  "body_text": "...",
  "publication_date": "YYYY-MM-DD",
  "author": "...",
  "url": "...",
  "tags": ["..."]
}
```

**Timestamp rule:** Use publication/release date, not meeting or event date. FOMC minutes timestamp = release date (3 weeks after meeting). NBER papers timestamp = posting date. Rationale: the system measures when ideas enter public discourse, not when privately held.

### Stage 2: Filtering and Deduplication

No topic filter needed — sources are macro-relevant by construction. Two operations only:

1. **Near-duplicate removal:** MinHash-based detection within rolling 48-hour windows. Removes wire redistributions and minor edits. Retain one canonical version per duplicate cluster.
2. **Date range filter:** Retain only documents with publication_date between 2010-01-01 and present.

### Stage 3: Embedding

**Model: `all-mpnet-base-v2` — locked, do not change.**

- Truncate to: headline + first 600 tokens of body text
- For documents over 2,000 words: split into overlapping 600-token chunks with 100-token overlap before embedding. Embed each chunk separately.
- Each chunk carries full document-level metadata.
- Store embeddings with chunk-to-document mapping preserved.
- Run on RCC (GPU partition). See infrastructure section.

**Look-ahead bias mitigation:** `all-mpnet-base-v2` is a general-purpose model (training cutoff ~2020–2021), not a finance-specialized model. Finance-tuned models (e.g., FinTextSim) would amplify look-ahead concerns on this domain. The tradeoff — marginally noisier clusters — is accepted.

**Mandatory sensitivity check (Phase 3):** Compare cluster quality and NMI across pre-2021 and post-2021 sub-periods. If clusters are dramatically cleaner post-cutoff, document as evidence of significant look-ahead and caveat accordingly.

### Stage 4: Clustering

BERTopic with dynamic topic modeling extensions.

**Locked parameters (from config.yaml — do not tune):**
```
UMAP:    n_neighbors=15, min_dist=0.1, n_components=5, metric='cosine'
HDBSCAN: min_cluster_size=20, min_samples=5, cluster_selection_method='eom'
Sensitivity sweep: min_cluster_size ∈ {10, 20, 40}
```

Three granularity levels:
- **Fine:** 200+ clusters
- **Medium:** 40–80 clusters — primary analysis unit; a "narrative" is operationally a medium-granularity cluster
- **Coarse:** 10–20 clusters

**Bootstrap stability evaluation:** 20 replicates with deterministic seeds. Report NMI and ARI across all pairs for each granularity level. **Kill criterion: NMI < 0.40 across all parameter settings → stop and investigate before proceeding.**

**Source-type contamination check (post-clustering diagnostic):** For each cluster, groupby source_tier. Clusters > 90% one source type are flagged for manual review — potential register-based rather than semantic clustering. One groupby operation; not an algorithmic correction.

**Look-ahead sensitivity check:** After clustering, compute NMI separately for pre-2021 and post-2021 sub-corpora. Document findings.

### Stage 5: Dynamics Fitting

Two volume signals feed this stage. They are kept separate and produce complementary outputs.

**Signal A — RavenPack press volume (primary dynamics series):** Weekly article counts from the ~30-outlet premium press whitelist. This is the primary series for SIR/logistic parameter estimation. Consistent, outlet-normalized, covers the full 2010–present window reliably. Stored in `data/dynamics/ravenpack/`.

**Signal B — Institutional corpus document counts (secondary dynamics series):** Per-cluster document counts from the 1A semantic corpus. Counts by document, not by chunk. This signal measures how quickly the analytical-institutional community engages with a narrative — a distinct and independently interesting dynamic that complements press volume. Stored alongside cluster output.

**Concordance between Signal A and Signal B is a finding:** If institutional discourse dynamics and press volume dynamics show similar R₀ and peak timing, that is evidence of rapid propagation from analytical framing into journalism. If they diverge — institutional engagement precedes press peak by weeks — that lag is itself a measurable feature of narrative transmission speed worth reporting.

For each narrative cluster:

1. Extract Signal B time series (institutional corpus documents per day, count by document not chunk)
2. Extract Signal A time series (RavenPack weekly volume for matched topic/event categories)
3. Apply 7-day centered moving average smoothing to both (bump to 21-day if noisy)
4. Apply **stratified smoothing** on Signal B — smooth institutional documents and think-tank documents separately to prevent quarterly BIS or IMF publications from spiking the series
5. Apply **calendar annotation** — flag FOMC meeting dates, BLS release dates, and major known macro events on the weekly series
6. Fit four parametric models in parallel on Signal A (primary): SIR, logistic, Gompertz, exponential
7. Fit logistic model on Signal B (secondary) for comparison
8. Use Bayesian inference with weakly-informative priors (PyMC) — produces full posterior distributions, not point estimates
9. **Volume normalization (Signal A):** Express weekly RavenPack counts as fraction of total RavenPack corpus articles that week. Makes R₀ comparable across years; absorbs outlet coverage expansion effects.

**Two-stage fitting threshold:** Apply parametric models only when a cluster exceeds **3 articles/week averaged over 4 consecutive weeks AND 50 cumulative articles** in Signal A. Below threshold: report descriptive stats only (first appearance, cumulative count, most recent document). Label as "pre-fitting" in dashboard. Do not force a fit on thin data.

### Stage 6: Stage Classification

Classify each narrative cluster into one of five life-cycle stages based on its fitted curve:

| Stage | Criteria |
|-------|----------|
| Pre-emergence | < 50 cumulative articles; R₀ poorly identified |
| Early-spread | R₀ > 1.0; currently in growth phase; peak day not yet reached |
| Peak | At or near maximum daily volume; growth rate near zero |
| Decay | Post-peak; declining article volume |
| Dormant | Very low volume; R₀ < 1; narrative effectively concluded |

Threshold values are pre-specified in config.yaml — do not modify without documenting as an ADR.

### Stage 7: Dashboard

Public web tool. Reads pre-computed static artifacts — no live computation at user request time. Two primary views:

**View 1 — Life-Cycle Viewer:** Select a narrative → see growth curve with fitted model overlaid, R₀ estimate with credible interval, current life-cycle stage, representative document titles from key moments with links to original sources.

**View 2 — Emerging Narratives Panel:** Three sections:
- *Currently emerging:* Narratives crossing from pre-emergence into early-spread within the past 7–30 days. Show R₀ estimate with credible interval, current document volume, sample titles.
- *Historical analogs:* For each emerging narrative, top 3–5 historical narratives with most similar early-stage trajectories.
- *Aggregate state:* Summary metrics — number of narratives per stage, dominant clusters.

**Stretch — Narrative Map:** 2D UMAP projection with cluster centroids labeled, zoom and click-to-explore. Cut this if time-constrained.

**Onboarding:** Persistent "what is this?" page explaining the framework in plain language with a worked example of a historical narrative life-cycle. Tooltips on R₀, stage labels, etc.

**Live update architecture:** Weekly cron job on RCC or small VPS. Pulls past week's documents, embeds, assigns to existing clusters or flags candidate new clusters, refits parameters on changed clusters, writes static JSON/HTML artifacts. Frontend (Hugging Face Spaces or Vercel free tier) reads only static artifacts. If a weekly update fails, display last-good state with prominent "last updated" timestamp — failure is visible, not hidden.

---

## 6. Current Project Status

### Completed

**Phase 1 — Pilot:** Complete. Bootstrap NMI passes kill criterion. Anchor narrative detection on three-narrative pilot set confirmed. Do not rerun or modify pilot code.

**Phase 2 — Data Pipeline:** Complete. Full historical ingestion (2010–present) ran on RCC under account `pi-dachxiu`. The ingested corpus includes institutional sources, AP News (Wayback CDX), and MarketWatch (Wayback CDX).

### In Progress

**Phase 3 — Embedding, Clustering, Dynamics:** Currently running on RCC. SLURM jobs for embedding were submitted but had dependency resolution issues at last check. Clustering and dynamics fitting have not yet completed.

---

## 7. Immediate Tasks for Claude Code

**First action: determine current Phase 3 state before doing anything else.**

```bash
# On RCC Midway3
squeue -u ehgarver
ls -lh /scratch/midway3/ehgarver/data/embeddings/ 2>/dev/null
ls -lh /scratch/midway3/ehgarver/data/clusters/ 2>/dev/null
sacct -u ehgarver --starttime=2026-05-01 --format=JobID,JobName,State,Elapsed
```

Report what's there before proceeding. The path forward depends on where Phase 3 actually is.

### If embedding is NOT yet complete (preferred path)

The corpus needs to be corrected before embedding runs. AP News and MarketWatch have been cut from the semantic corpus (see Section 4). Do the following:

1. **Update `whitelist.yaml`:** Move AP News and MarketWatch from active sources to `archived_sources` section with note: "journalism tier removed 2026-05-11; institutional+analytical corpus only; these sources remain in ingested raw data but are excluded from embedding and all downstream stages."

2. **Filter the processed corpus:** Before embedding, filter `data/processed/` to exclude documents where `source` is `ap_news` or `marketwatch`. Write a script `scripts/filter_corpus_pre_embed.py` that reads the processed JSONL, drops those source types, writes a filtered JSONL to `data/processed/corpus_for_embedding.jsonl`, and reports counts before/after.

3. **Add CFR to the source list:** If CFR (Council on Foreign Relations) is not already in `whitelist.yaml` and `src/mnd/ingestion/institutional.py`, add it. RSS feed: `cfr.org/rss/all`. Same pattern as Brookings/PIIE.

4. **Add FEDS Notes explicitly:** Confirm `federalreserve.gov/econres/feds/` is in the Fed ingestor scope. FEDS Notes are short analytical notes from Board economists — distinct from working papers and speeches. If not present, add as a source type under the Fed ingestor.

5. **Re-run ingestion for CFR and FEDS Notes if missing**, then proceed to embed the filtered corpus.

6. **Submit embedding job:** `sbatch scripts/rcc/embed_rcc.sh` on the filtered corpus.

### If embedding IS complete but clustering has not run

1. Apply the corpus filter retroactively: before passing embeddings to BERTopic, load the embedding matrix, filter rows where the corresponding document's source is `ap_news` or `marketwatch`, and proceed with the filtered embedding matrix. Write this as a preprocessing step in the cluster pipeline.

2. Add CFR and FEDS Notes ingestion for historical data if not already present. These will be included in Phase 6 live updates.

3. Proceed with clustering on filtered embeddings.

### If clustering IS complete

Proceed with current corpus as-is. Document the AP News / MarketWatch inclusion in methodology (they are now out of scope for live updates). Implement source corrections for Phase 6.

### Regardless of Phase 3 state — additional tasks

**Media Cloud integration:** Add Media Cloud as the detection layer. This is new and was not in the prior architecture. It does not affect the semantic corpus or embedding — it is a separate signal pipeline.

- Add `src/mnd/detection/mediacloud.py`
- Queries the Media Cloud API for story count time series by keyword/topic
- Output: daily story counts per keyword query, stored as `data/detection/mediacloud_{query}_{date_range}.jsonl`
- Used in Phase 6 to flag candidate emerging narratives before institutional sources have characterized them
- API key goes in `.env` as `MEDIACLOUD_API_KEY`
- Do not integrate into the main embedding/clustering pipeline — this is a parallel detection signal

**Push all commits:** After any changes, commit and push to origin. Confirm remote is up to date. Every session should end with a push.

**RCC discipline:** All jobs submit under `--account pi-dachxiu`. All data writes to `/scratch/midway3/ehgarver/` only — never to the PI's project folder. Be conservative with resource requests. Embedding: GPU partition, 1 GPU, 32GB RAM, 12h wall time. Clustering: caslake partition, CPU only, 64GB RAM, 8h wall time.

---

## 8. Remaining Phases

### Phase 4 — Validation

Do not begin until Phase 3 NMI and ARI results are in hand and pass kill criteria.

1. **Pre-registration:** Commit `prereg/PREREGISTRATION.md` to a public timestamp (GitHub or OSF) before examining any outcome data. This document specifies all hypotheses, variables, statistical tests, and decision criteria. Must be done before any FRED data is correlated against narrative clusters.

2. **Anchor narrative recovery:** System must recover all 10 anchor narratives within 14-day tolerance. See anchor list in Section 9.

3. **Fizzled-narrative validation:** For each anchor, validate that contemporaneous narratives that did not crystallize receive appropriately different stage classifications.

4. **Sensitivity analysis:** Run three pre-specified parameter settings (strict: min_cluster_size=10, default: 20, permissive: 40). Core conclusions must hold across all three.

5. **Exploratory predictive analysis (compressible):** Granger causality testing in both directions, FDR-corrected with Benjamini-Hochberg. Report null results honestly if no associations survive correction — this is not a project killer.

**Kill criteria for Phase 4:**
- Fewer than 7 of 10 anchor narratives recovered within 14-day tolerance → debug embedding/filtering; if persistent, shift to novelty-velocity framework
- Median R² < 0.30 across validation narratives OR R₀ posterior CIs spanning > 2 units → drop SIR; fall back to logistic growth or non-parametric curve features

**Out-of-sample discipline:** Training data 2010–2019. Held-out validation 2020–present. The held-out period is not examined until final analysis. All hyperparameters locked before held-out evaluation.

### Phase 5 — Dashboard Build

1. Streamlit (MVP) or React/Next.js single-page app
2. Static cached artifacts produced by analysis pipeline (JSON cluster data, fitted parameters, stage classifications, representative document titles and URLs)
3. Implement View 1 (Life-Cycle Viewer) and View 2 (Emerging Narratives Panel)
4. Onboarding "what is this?" page with worked historical example
5. Deploy to Hugging Face Spaces (free tier, public URL, no auth required)

### Phase 6 — Live Updating

Weekly cron job. Pulls past week's documents from all active sources (institutional, think tanks, VoxEU, Media Cloud detection signal). Embeds new documents. Assigns to existing clusters or flags as candidate new clusters. Refits parameters on changed clusters. Writes static artifacts.

Sources active in live updates (beyond historical corpus sources):
- NBER: RSS feed for new working paper abstracts
- SSRN: RSS feed for new macro/finance submissions

These were removed from historical ingestion but their RSS feeds provide genuinely fast signals for live updating. Include them in the weekly cron only.

Robust failure handling: if a weekly job fails, dashboard displays last-good state with "last updated" timestamp. Failure is visible, not hidden.

### Phase 7 — Writeup and Reproducibility

1. GitHub repository: pinned dependencies (`requirements.txt`), clear README, replication instructions, pre-registration document, anchor narrative ground truth CSV/JSONL
2. Short technical report: 5–8 pages describing methodology and findings
3. Stretch: 12–15 page workshop-paper quality writeup for submission to ACL Economics and NLP or NeurIPS ML for Finance workshop

---

## 9. Locked Parameters

**Do not change any of these without creating a new ADR in `docs/architecture_decisions.md`.**

```yaml
embedding_model: all-mpnet-base-v2        # locked; do not change
article_truncation_tokens: 600             # headline + first 600 tokens
chunk_size_tokens: 600
chunk_overlap_tokens: 100
chunk_threshold_words: 2000               # documents above this are chunked

umap_n_neighbors: 15
umap_min_dist: 0.1
umap_n_components: 5
umap_metric: cosine

hdbscan_min_cluster_size: 20             # default; sweep {10, 20, 40}
hdbscan_min_samples: 5
hdbscan_cluster_selection_method: eom

smoothing_window_days: 7                 # centered MA; bump to 21 if noisy
bootstrap_replicates: 20
anchor_tolerance_days: 14
pre_emergence_threshold_articles: 50
early_spread_r0_threshold: 1.0

fitting_threshold_articles_per_week: 3   # over 4 consecutive weeks
fitting_threshold_cumulative: 50

train_cutoff: 2019-12-31                 # training data ends here
holdout_start: 2020-01-01               # held-out validation starts here

random_seed: pinned in config.yaml       # specific values there
```

---

## 10. Anchor Narratives (FINAL — 10 narratives)

FTX collapse and GameStop short squeeze were removed (out of macro scope). Taper tantrum and China devaluation were added.

| # | Narrative | Reference Date | Why It Anchors |
|---|-----------|---------------|----------------|
| 1 | SVB collapse | 2023-03-09 | Entity-rich, sharp emergence, well-documented |
| 2 | COVID market crash | 2020-02-24 | Largest single-narrative event in window |
| 3 | Brexit aftermath | 2016-06-24 | Long-tail narrative with clear ignition |
| 4 | Transitory inflation debate | 2021-Q2 | Slower, diffuse, well-documented Fed language |
| 5 | Credit Suisse stress | 2023-03-15 | Adjacent to SVB; tests cluster differentiation |
| 6 | Regional banking contagion | 2023-03-13 | Tests narrative branching from anchor events |
| 7 | 2022 inflation peak narrative | 2022-Q2/Q3 | Multi-month evolving narrative |
| 8 | Soft landing emergence | 2023-Q3/Q4 | Slow emergence; uncontested timing |
| 9 | 2013 taper tantrum | 2013-05-22 | Bernanke Senate testimony; tests 2010–2015 window |
| 10 | 2015 China devaluation scare | 2015-08-11 | PBOC devaluation announcement; global contagion framing |

---

## 11. Kill Criteria

Pre-committed thresholds. If hit, stop and respond as specified — do not continue.

| Criterion | Threshold | Check Point | Response |
|-----------|-----------|-------------|----------|
| Cluster stability | Bootstrap NMI < 0.40 across all parameter settings | End of Phase 3 | Investigate; if unsalvageable, narrow to inflation-only fallback scope (2018–present) |
| Anchor recovery | Fewer than 7 of 10 anchors recovered within 14-day tolerance | End of Phase 4 | Debug; if persistent, shift to novelty-velocity framework |
| Dynamics fit quality | Median R² < 0.30 across validation narratives OR R₀ CIs > 2 units | End of Phase 4 | Drop SIR; fall back to logistic or non-parametric curve features |
| Predictive null | No associations survive FDR correction | Phase 4 | Not a project killer — report null honestly as exploratory finding |
| Live update reliability | > 25% of weeks fail | Phase 6 month 1 | Degrade to monthly updates; make "last updated" prominent |
| Time budget | MVP not complete by month 3 from now | Mid-project | Cut from stretch downward; preserve MVP above all else |

**Fallback scope:** If multiple kill criteria trigger stress during Phase 3–4, narrow to inflation discourse only, 2018–present. Corpus halves, semantic homogeneity increases, look-ahead window shortens, CPI/PCE validation becomes cleaner. Methodology, dashboard, and tooling all transfer unchanged.

---

## 12. Infrastructure

**Compute:** UChicago RCC Midway3
- Account: `pi-dachxiu` (PI's account; use conservatively)
- Scratch directory: `/scratch/midway3/ehgarver/` — all data here
- Never write to PI's project folder
- GPU partition for embedding; caslake (CPU) for clustering
- SLURM scripts in `scripts/rcc/`

**Environment variables required (`.env`):**
```
FRED_API_KEY=...
WRDS_USERNAME=...
WRDS_PASSWORD=...
MEDIACLOUD_API_KEY=...
```

**Removed env vars (no longer needed):**
- `PROQUEST_DATASET_ID` — remove
- `NEWS_API_KEY` — remove
- `WRDS_MFS_*` (JLN indices) — remove; JLN replaced by EPU

**Data paths:**
- Raw documents: `/scratch/midway3/ehgarver/data/raw/`
- Processed corpus: `/scratch/midway3/ehgarver/data/processed/`
- Embeddings: `/scratch/midway3/ehgarver/data/embeddings/`
- Clusters: `/scratch/midway3/ehgarver/data/clusters/`
- RavenPack dynamics (Signal A): `/scratch/midway3/ehgarver/data/dynamics/ravenpack/`
- Institutional dynamics (Signal B): `/scratch/midway3/ehgarver/data/dynamics/institutional/`
- Media Cloud detection signals: `data/detection/mediacloud/`
- Validation data: `data/raw/validation/` (local; FRED and EPU pulls are small)
- Anchors: `data/anchors/anchor_narratives.jsonl`

**Archived sources (do not delete, do not reactivate):**
- `src/mnd/ingestion/gdelt.py` → `scripts/archive/`
- Common Crawl ingestor → `scripts/archive/`
- ProQuest export script → `scripts/archive/`

---

## 13. Statistical Reporting Standards

- All quantitative claims report 95% bootstrap confidence intervals
- All multiple-comparison contexts report both raw p-values and Benjamini-Hochberg corrected significance
- Any predictive analysis additionally reports Deflated Sharpe Ratio if portfolio-style framings are used
- Null results reported honestly — a null exploratory finding is still a finding

---

*Document version: 2026-05-11 rev2. Supersedes all prior CLAUDE.md corpus architecture sections, source specifications, and ingestion instructions. Changes from rev1: RavenPack restructured as Layer 1B journalism supplement (primary dynamics series); Media Cloud moved to standalone Layer 2 detection; Layer 3 validation data updated — JLN replaced by EPU (Baker-Bloom-Davis); Stage 5 dynamics fitting updated to reflect dual-signal approach (RavenPack Signal A primary, institutional corpus Signal B secondary); data paths updated accordingly. The project plan PDF remains valid for theoretical framework and methodology; this document takes precedence on source architecture and current status.*
