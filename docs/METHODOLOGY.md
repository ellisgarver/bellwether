# Macro Narrative Dynamics — Methodology

A plain-English walkthrough of how the system works and why each step is built the way it is. This document sits between the engineering-focused `CLAUDE.md` (what to do when writing code) and the comprehensive `MND_PROJECT_SPEC.md` (full project specification). It is the canonical reference for "how does this project actually work?" — useful for collaborators, reviewers, and future development sessions.

The methodology is designed to be **defensible without relying on researcher judgment**. Every parameter is either a published library default, a citation from primary literature, or removed because no field-accepted anchor existed. There are no sensitivity sweeps. There are no hand-tuned thresholds. This is a stated design constraint, not an aspiration — see "Methodological principles" at the bottom.

---

## 1. What we're measuring

We're measuring how macro-financial narratives — like "the Fed is engineering a soft landing", "inflation is transitory", "regional banks are at risk" — form, spread, peak, and fade in U.S. policy discourse over 2010-present.

This is an **educational, historical, and analytical** project. It is not a predictive trading tool, not a parameter-exploration paper, and makes no causal claims. The value is in helping a reader understand *how* macro discourse evolves — when narratives ignite, how fast they spread, when they peak, what they look like as they fade, and what historical narratives the current ones most resemble.

**Core intellectual frame**: Robert Shiller's *Narrative Economics* (2017, 2019) argues that economic narratives spread through populations in patterns resembling epidemics. He left the formal measurement of that claim as future work. This project operationalizes the *lifecycle dynamics* half of Shiller's framework — emergence, growth, peak, decay — by fitting SIR/logistic ODEs to BERTopic cluster volume. We do not claim to measure narrative virality at the population level or causal effects on macro outcomes; that is left to structural work in the Flynn & Sastry (2024) tradition.

**Why this matters**: macro narratives drive expectations, expectations drive policy, policy drives outcomes. Measuring the narrative layer directly — separately from market prices or survey data — gives a complementary view on the formation of macro consensus. The institutional/policy/academic discourse measured here is the *upstream supply side* of the narratives that households eventually adopt — a layer that Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming, *Review of Economic Studies*) showed differs qualitatively from household-elicited narratives.

**Field context**: Roos & Reccius (2024, *Journal of Economic Surveys*) — the most recent survey of narrative economics — notes the field is still consolidating, with no generally accepted definition of an "economic narrative" and no operationalization of Shiller's framework that goes beyond keyword counts. Among published quantitative work, the closest precedents are Bybee, Kelly, Manela & Xiu (2024, *Journal of Finance*) and Larsen & Thorsrud (2019, *Journal of Econometrics*) on the topic-model side, Bertsch et al. (2021, *Economics Letters*) on the temporal-dynamics side, and Hansen, McMahon & Prat (2018, *QJE*) on the institutional-text side. None combine multi-source institutional+academic corpus, lifecycle ODE fitting, BERTopic-on-transformer-embeddings, and live public reporting in a single artifact. See `docs/related_work.md` for the full survey.

---

## 2. The narrative-as-epidemic analogy

The conceptual leap: a narrative is something that spreads from writer to writer the way a disease spreads from person to person. A writer encounters a framing (susceptible state), starts using it (infected), and either keeps spreading it or moves on (recovered). Aggregate over thousands of writers, plot weekly volume of articles using the framing, and you get a curve that looks remarkably like an epidemic curve — sharp ignition, exponential growth, peak, decay.

This isn't just metaphor. The SIR model (Kermack & McKendrick 1927) — three populations of Susceptible, Infected, and Recovered with two rate constants β (transmission) and γ (recovery) — fits narrative volume curves the same way it fits disease incidence. The basic reproduction number R₀ = β/γ has the same interpretation: above 1 the narrative spreads, below 1 it fades.

We're not the first to apply SIR to narrative spread. There is established literature on epidemic-style modeling of news propagation, misinformation spread, and rumor diffusion. We're applying it to a substrate — institutional macro discourse — where it hasn't been measured rigorously before.

---

## 3. The pipeline

A single document moves through the system in eight stages.

### Stage 1 — Ingestion (basis set, ADR-020)

The corpus is a **basis set**: the minimum set of sources spanning every independent dimension of US macro discourse, with no redundant or noise-dominated entries. Twelve active ingestors map 1:1 to eight dimensions:

| Dimension | Source(s) |
|---|---|
| 1. US monetary authority | Federal Reserve Board (FOMC, speeches incl. Jackson Hole, Beige Book, FEDS Notes, MPR, FSR) |
| 2. US monetary research | Regional Feds — NY (Liberty Street + Staff Reports via RePEc/IDEAS, ADR-025), SF (Economic Letter, Working Papers, FedViews, Beige Book, Community Development; cross-posts excluded, ADR-034), Chicago (multi-series incl. president speeches + business/economic-conditions surveys CFSBC/CFSEC), Atlanta (macroblog + working papers) |
| 3. International macro authority | IMF (WEO, GFSR, F&D, working papers, blog) |
| 4. International central-bank network | BIS (Quarterly Review, working papers, Bulletins, curated CB speeches) |
| 5. US fiscal authority | CBO (legislative scoring + outlook + working papers + MBR) + **CEA** (executive — Economic Report of the President via govinfo.gov ERP) |
| 6. US financial-stability research | Treasury OFR (working papers, FSOC reports) |
| 7. US policy think-tank | Brookings (Economic Studies + Hutchins Center) + PIIE (international policy) |
| 8. Academic primary work + column | **NBER** (working papers via direct URL enumeration) + VoxEU (CEPR columns) |
| Cross-cutting Q&A register | Congressional Treasury Secretary testimony |

**Why this is a basis set.** Each source spans a dimension no other source covers. Multiple sources on the same dimension (e.g., the 4 regional Feds for dimension 2, or Brookings + PIIE for dimension 7) cover distinct sub-axes within that dimension. Sources whose dimensional coverage was wholly redundant with another source — most consequentially **CFR**, whose macro subset is captured by PIIE on dimension 7 and whose ~80% foreign-policy non-macro content is just noise — were removed (ADR-020).

**Why these are upstream sources.** These are where macro narratives *form* — among policymakers, researchers, and analysts — *before* the financial press picks them up. Financial journalism (WSJ, Bloomberg, FT) is downstream of this discourse. We're studying narrative formation, not propagation by the press, so we ingest the upstream layer.

**Why not the press as text.** Two reasons. First, premium analytical press is paywalled and not bulk-licensable. Second, ingesting press text would bias toward narratives that already broke through to journalism, missing the earlier formation phase that's the analytical target. We *do* capture press volume separately — see Stage 6 — but we don't ingest the text.

**Why not govinfo.gov for CBO.** govinfo.gov has a CBO collection (~772 publications) but GPO-deposit coverage is uneven over time (41 records 2010 → 6 records 2024), which would inject a non-random, time-varying selection filter into the CBO volume signal — exactly the artifact the basis-set framing was designed to eliminate. The Wayback bounded publication-ID enumeration path (ADR-023, supersedes the ADR-017 Playwright approach) covers the full cbo.gov archive directly. Engineering complexity is the cost we pay for methodological cleanliness.

**What we don't include.** Paywalled databases (no ProQuest, Factiva, Bloomberg, RavenPack); the financial press itself as embeddable text (no AP, Reuters, MarketWatch corpus); SSRN (no public historical archive); CFR (basis redundancy with PIIE).

Ingestion is **content-neutral** — every article from every active basis-set source enters the corpus regardless of topic. There is **no pre-clustering topical filter** (ADR-020).

### Stage 2 — Filter (date range + dedup only, ADR-020)

The filter stage does exactly two things:
1. Restrict to publication dates in [2010-01-01, today].
2. Remove near-duplicates within rolling 48-hour windows using MinHash (Broder 1997 / Henzinger 2006 threshold 0.85).

**No topical keyword filter is applied.** The basis-set source selection (Stage 1) is the only macro-scope constraint at ingest time. Topical relevance is decided post-clustering by a JEL-classifier step (Stage 5b below), applied symmetrically across sources using the AEA's published JEL taxonomy.

**Why no keyword filter at this stage.** The previous design (ADR-015 → 016 → 018) used a 213-keyword JEL-anchored gate to determine macro relevance over title + body. That design had two problems. First, every basis-set source's institutional mandate is already in macro scope by construction, so the keyword gate was a second filter applied on top of the source filter — double-filtering. Second, mapping JEL categories to specific keywords required researcher judgment about which keywords represent each code — exactly the kind of judgment that's hard to defend without a field-standard anchor. ADR-020 dropped the apparatus and shifted JEL classification post-clustering, where the cluster level provides enough content to apply a published taxonomy without intermediate keyword choices.

The pre-reg sentence becomes: *"No pre-clustering topical filter is applied. The basis-set source selection is the only macro-scope constraint at ingest. Topic relevance is decided post-clustering by assigning each BERTopic cluster a primary JEL code from the AEA's published taxonomy, applied symmetrically across sources."*

### Stage 3 — Chunking

Documents that fit within 512 tokens of the embedding model's context window pass through unchanged. Longer documents — FOMC minutes (~12,000 words), BIS Quarterly Review articles (~6,000 words), IMF flagship chapters (~8,000 words) — are split into overlapping 512-token chunks with ~64-token overlap.

**Why 512 tokens?** This is the established retrieval unit in the field. The BEIR benchmark (Thakur et al. 2021, NeurIPS) — the de facto standard for evaluating retrieval models — uses "only the first 512 word pieces within all documents" across every dataset.

**Why chunk at all?** A 12,000-word FOMC minutes document contains multiple distinct narratives within it: staff economic outlook, participants' views on inflation, forward-guidance discussion. If we embedded the whole thing as one vector, those narratives would average out and the document would land in some bland centroid that doesn't represent any one of them. Chunking gives each narrative inside a long document its own embedding.

**Why these specific numbers?** They're field-standard, not researcher-chosen. We cite them.

### Stage 4 — Embedding

Each chunk goes through **Qwen3-Embedding-8B** (ADR-036), an open-source transformer model that turns text into a 4096-dimensional numerical vector capturing its semantic content. Documents about the same narrative end up near each other in the 4096-dimensional space; documents about different narratives end up far apart.

**Why this model?** Top performance on the MTEB embedding benchmark, Apache 2.0 license, instruction-aware (we prefix each chunk with "Represent this financial policy document for narrative clustering", biasing the vector toward semantic content rather than writing style), and native 32k-token context window (so it handles long inputs gracefully).

**No second model.** The previous design used a comparator embedder (mpnet) as a look-ahead sensitivity check. That sensitivity-check apparatus is researcher-introduced rigor that the new methodology principle (anchored-or-removed) explicitly excludes. The negative finding from the original look-ahead check is preserved in the project history as evidence, not as a methodology element.

### Stage 5 — Clustering

We run **BERTopic** (Grootendorst 2022), the field-standard pipeline for transformer-based topic discovery. Internally it does three things:

1. **UMAP** — reduces the 4096-dim embedding vectors to 5 dimensions while preserving cluster structure. Think of this as squashing a high-dimensional cloud of points into a lower-dimensional shape that's easier to find clusters in.
2. **HDBSCAN** — finds the dense regions in the 5-dim space. Each dense region is a cluster (a narrative). Sparse regions are "outliers" — documents that don't belong to any clear narrative.
3. **c-TF-IDF** — for each cluster, extracts the most distinguishing words (the words that appear unusually often in this cluster compared to others). These become the cluster's algorithmic name.

**Every parameter is BERTopic's library default**, cited from Grootendorst (2022). No hand-tuning, no sensitivity sweeps. Whatever clusters emerge are what we report.

**One granularity, not three.** The previous design merged clusters into three hierarchical levels ("fine", "medium", "coarse") at researcher-chosen silhouette thresholds. That layered structure had no literature anchor — published topic-model narrative studies (Bybee, Kelly, Manela & Xiu 2024 "Business News and Business Cycles"; Hansen, McMahon & Prat 2018 *QJE*; Larsen & Thorsrud 2019 *Journal of Econometrics*; Bertsch, Hull, Lumsdaine & Zhang 2021 *Economics Letters*) all report at a single granularity. We follow that precedent.

**Naming**: every cluster gets two names. The **algorithmic name** is its top 5-10 c-TF-IDF terms joined — e.g., `inflation, transitory, supply-chain, base-effects, Powell, FOMC`. This is the canonical identifier used for all queries and analysis. Optionally, an LLM can generate a **human-readable display label** ("Transitory inflation debate, 2021") for the dashboard UI. The display label is cosmetic only — it never enters any calculation. If a reviewer asks "how did you name this narrative", the answer is: "We didn't — it has an algorithmic top-term list; the display label is post-hoc UI."

### Stage 5b — Post-clustering JEL classification (ADR-020)

After BERTopic produces clusters, we assign each cluster a primary **JEL code** from the American Economic Association's published Journal of Economic Literature classification (https://www.aeaweb.org/econlit/jelCodes.php). The procedure:

1. For each cluster, take its top c-TF-IDF terms (the BERTopic representation of the cluster).
2. For each top-level JEL code (A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, Y, Z), take the AEA's verbatim published description.
3. Embed both the cluster term joinder and the JEL descriptions in the same Qwen3 space used for the clustering itself.
4. Assign the cluster the JEL code whose prototype is the nearest cosine neighbor.

Clusters with primary JEL in the **macro-finance scope** — codes **E** (Macroeconomics and Monetary), **F** (International), **G** (Financial), **H** (Public Economics, including fiscal H6) — are retained for the dynamics analysis (Stages 6-8). Clusters outside this scope (e.g., a cluster of labor-market papers landing in J, or healthcare papers landing in I) are reported with their JEL label and **excluded from dynamics fitting only** — they are NOT dropped from the embedded corpus. The full clustering output is preserved for diagnostic and replication purposes.

**Why this is defensible.** JEL is a published, externally-maintained taxonomy that the AEA itself uses to classify journal submissions. We do not invent it, edit it, or add to it. We do not pick keywords that "represent" each code. We embed the AEA's own descriptions and let cosine similarity do the assignment — the same operation that drove the clustering in Stage 5. The macro-finance scope {E, F, G, H} is the standard mapping used in macro-finance research; if a reviewer asks "why these four codes", the answer is the JEL system's own definitions.

**Why post-clustering and not pre.** Cluster-level content (typically 100-1000 documents per cluster, with their c-TF-IDF terms) provides much more signal than a single article's title + body, so classification at the cluster level is more reliable. And applying the classifier post-clustering means we never bias the embedding/clustering step toward any particular topic taxonomy.

**Diagnostic.** The classifier outputs a `runner_up_gap` for every cluster — the cosine-similarity difference between its primary and second-best JEL code. A median gap below 0.05 across all clusters would indicate the classification is ambiguous; in that case we'd revisit (likely by expanding the JEL prototype text to include subcodes). The diagnostic ships with the JEL classifier output.

### Stage 6 — Volume signals (institutional + press)

For each narrative cluster, we build three weekly volume time series.

**(a) Institutional volume** — count of articles in this cluster published per week. This is the primary signal: how much our upstream institutional sources are talking about this narrative.

**(b) Premium press volume** — we query the **Media Cloud API** (Layer 1B in the system) against a curated premium-press outlet collection (WSJ, Bloomberg, FT, Reuters, NYT, Barron's, Dow Jones Newswires, MarketWatch). The query is the cluster's top 5-10 c-TF-IDF terms joined with Boolean OR — fully reproducible from clustering output, no human input. Output: weekly count of premium-press stories matching this query.

**(c) Broad press volume** — same Media Cloud machinery, queried against the broader Media Cloud catalog (thousands of outlets). Detection-only signal: catches narrative emergence in broad press even before institutional sources have clustered it.

**Why three signals?** Cross-validation and lead-lag analysis.
- **Cross-validation**: a real macro narrative shows up in *both* institutional discourse AND premium press. If a cluster has institutional volume but zero press volume, it might be a procedural artifact (e.g., routine Treasury announcements that don't reach narrative status). If press volume but no institutional, it's downstream-only — out of our analytical scope.
- **Lead-lag**: institutional discourse usually *leads* premium press by days to weeks. Plotting both curves on the same axis lets a reader literally see "the Fed was talking about soft landing for three months before WSJ wrote about it." This is the headline analytical insight the project enables.
- **Detection**: broad-press spikes can flag emerging narratives in Phase 6 weekly updates before they reach our institutional sources.

**Media Cloud never enters embedding or clustering.** It is a separate volume signal, not a text source. We use it for cross-validation and as a parallel curve on the dashboard.

Each curve is smoothed with a 7-day centered moving average to remove the weekend drop-off in daily news output (the natural weekly cycle for daily count data — Shumway & Stoffer, standard time-series practice).

### Stage 7 — Dynamics fitting

For each cluster with enough volume to support a fit (a minimum cumulative count and a minimum sustained rate — thresholds documented separately), we fit two classical diffusion models to the smoothed weekly institutional volume curve:

**Logistic curve** (Verhulst 1838) — the classic S-shaped growth-then-saturation curve, parameters: carrying capacity *L*, growth rate *k*, midpoint *t₀*.

**SIR model** (Kermack & McKendrick 1927) — three compartments (Susceptible, Infected, Recovered), two rate parameters β (transmission) and γ (recovery), yielding the basic reproduction number **R₀ = β/γ**. R₀ > 1 means the narrative is spreading; R₀ < 1 means it's fading.

Fitting is done with Bayesian inference (PyMC) using weakly-informative priors elicited from the established epidemic-modeling literature (Bjørnstad 2018, *Epidemics: Models and Data using R*; Gelman et al. *BDA3*). We report the posterior distribution over R₀, not just a point estimate, so the confidence interval is part of the output.

**Why classical models?** They're a century old, well-understood, and the right level of complexity for this measurement. We're not building a new model; we're applying established ones to a new substrate. Direct citations to Kermack-McKendrick (1927) and Verhulst (1838) — no novel methodology to defend.

### Stage 8 — Stage classification

Each fitted narrative is labeled with one of four lifecycle stages, determined purely by R₀ direction and basic volume thresholds:

- **Pre-emergence** — too little volume to fit reliably; descriptive statistics only
- **Growth** — R₀ > 1; the narrative is actively spreading
- **Decay** — R₀ < 1; the narrative is fading
- **Dormant** — past peak by months, with low residual volume

The R₀ = 1 threshold is the classical epidemic threshold from SIR theory (Kermack & McKendrick 1927). The previous design added arbitrary thresholds for "peak window ±14 days", "decay = 30% below peak", "dormant = ≤1 article/day rolling average". Those had no literature anchor and were removed.

---

## 4. Validation — does the system recover known narratives?

We maintain a small set of **anchor narratives**: 10 macro events spanning 2010-2023 with documented ignition dates and primary-source citations. Each anchor is something a reader would recognize as a major macro narrative — SVB collapse (2023-03-09), COVID market crash (2020-02-24), Brexit (2016-06-24), the transitory inflation debate (2021-Q2), Credit Suisse stress (2023-03-15), regional banking contagion (2023-03-13), 2022 inflation peak (Q2-Q3), soft landing emergence (2023-Q3-Q4), 2013 taper tantrum (2013-05-22), 2015 China devaluation scare (2015-08-11).

For each anchor, we check: did the clustering produce a narrative whose volume spike lands within ±14 days of the documented ignition date? The ±14-day window is Brown & Warner 1985's event-study convention from financial economics.

**We report the recovery rate as an output, not as a pass/fail kill criterion.** A binary cutoff like "7 out of 10 = pass" would be a researcher-set threshold with no anchor. Reporting the rate is the honest version: here's what fraction of known events the system recovered, with details on each one.

**Anchors are validation only.** They are never used for filter training, embedding fine-tuning, hyperparameter selection, or any other choice that affects what the system finds. Their only role is to score the system after the fact.

---

## 5. Output — similar past narratives

For each detected narrative, the dashboard surfaces the **most similar past narratives** from the full historical narrative set (every cluster ever detected, not just anchors). Three complementary similarity measures:

| Measure | What it captures | Method |
|---|---|---|
| **Semantic** | "About the same topic" | Cosine similarity between cluster embedding centroids |
| **Lexical** | "Same vocabulary" | Jaccard overlap on top-K c-TF-IDF terms |
| **Morphological** | "Spread the same way" | Pearson correlation on normalized weekly volume curves |

We report the **top-5 most similar narratives by each method separately** rather than a single combined score. Top-K avoids the "where's the threshold" question — it's a ranking. The three views are complementary: morphological can surface narratives that share no vocabulary but had similar epidemic shapes (a 2022 inflation peak and a 2008 commodity-price spike, for instance).

This is what lets the dashboard answer: "this current narrative looks like it might be following the same arc as X past narrative." Educational and historical, not predictive.

---

## 6. The dashboard

The final product is a public web tool with three main views.

### Main view — Emerging Narratives

The actionable landing page: "what's happening now that's worth watching?"

- Filtered to narratives in **pre-emergence** or **growth** stages
- Sorted by recent acceleration (4-week velocity, or current R₀)
- Per narrative card:
  - Human-readable display name + algorithmic top terms
  - Three growth curves overlaid: institutional, premium press, broad press
  - Current R₀ + fitted carrying capacity
  - Calendar event markers (FOMC, CPI, etc.) on the time axis
  - Compact "Similar past narratives" panel — five thumbnails with mini-curves

A reader scanning this page sees: which narratives are currently forming or accelerating, what they look like in institutional discourse vs press, and what historical narratives most resemble them.

### Landscape view — 2D narrative map

The structural view: "what's the shape of macro discourse?"

A 2D UMAP projection of every narrative cluster's centroid (one dot per narrative, not per article — keeps it readable). Color encodes lifecycle stage, size encodes cumulative volume. Hovering shows a name and a mini-curve; clicking opens the narrative detail page. A time toggle animates the scatter to show how the landscape has evolved.

This is where the user discovers structure — clusters of related narratives sit near each other (the "banking-stress family" of SVB + Credit Suisse + Regional + First Republic all cluster together in 2D space, even though each is a distinct narrative).

### Timeline view — historical overview

The retrospective view: "what was happening in [period]?"

X-axis: date, 2010-present. Y-axis: narrative clusters, grouped by family. Volume shown as band height/intensity. Vertical markers for major macro events. Brush-to-zoom for focusing on specific periods (e.g., the March-April 2023 banking-stress cascade). Toggleable layers for institutional volume vs press volume.

Useful for retrospective analysis and for the educational mission — a reader can rewind to any moment in the 2010-present window and see what macro discourse looked like.

### Plus

- Per-narrative drill-down page (representative articles, full curves, similarity diagnostics, raw data)
- Compare mode (select 2-4 narratives, overlay their normalized growth curves)
- Anchor validation page (methodology transparency: all 10 anchors with recovered cluster IDs, ±14-day match status)

---

## 7. Methodological principles

These are the standing rules that govern every methodology choice. Adopted to make the system defensible without researcher judgment.

1. **Every parameter is anchored or removed.** Each value in the pipeline is either (a) a published library default, cited; (b) a primary-literature value, cited; or (c) removed because no field-accepted anchor exists. There are no "we picked this because it worked well" parameters.

2. **No sensitivity sweeps.** Sweeps were researcher choice masquerading as rigor. We fix on field-accepted single values.

3. **No pass/fail kill criteria with arbitrary thresholds.** Quantities (anchor recovery rate, NMI, R², R₀ confidence width) are reported, not gated. Reviewers can apply their own thresholds.

4. **No pre-clustering topic filter (ADR-020).** Topic relevance is decided in exactly one place — the post-clustering JEL classifier (`jel_classifier.py`), which assigns each cluster to its nearest AEA JEL prototype and drops clusters outside {E,F,G,H} from *dynamics only*. The only ingest-time filters are the 2010-present window and URL/content dedup; per-source keyword/title gates were removed because they were researcher-curated and asymmetric across sources.

5. **No hierarchy tiers.** One granularity, BERTopic default output. Multi-tier merging was researcher-introduced structure.

6. **Validation anchors are validation only.** They never influence the filter, the embedding, the clustering, or any hyperparameter. Their only role is to score outputs.

7. **Field-standard taxonomies over researcher-curated lists.** The JEL Classification System anchors the filter. The BEIR convention anchors the chunk size. The BERTopic library defaults anchor the clustering.

8. **Anchored or removed applies to abandoned pieces too.** Source ingestors, code paths, config blocks, and architectural pieces that have been abandoned are deleted from the active pipeline, not left commented out.

9. **No formal pre-registration; no train/test split (ADR-040).** Credibility rests entirely on principles 1–8 above — every parameter field-anchored, nothing hand-tuned (especially never toward anchor recovery). With zero tuning there is no fitted-on-train quantity a held-out boundary could catch overfitting on, so the pipeline runs over the full 2010-present corpus with no 2010-2019/2020+ split, and there is no registered analysis plan (no OSF, no locked timestamp). The project stays paper-writeable — tied to respected methods and citations — without that apparatus.

10. **Dynamics are shown as four complementary lenses, not a single selected model (ADR-039).** Every in-scope cluster is fit by logistic (Verhulst 1838), SIR (Kermack & McKendrick 1927), and Bass diffusion (Bass 1969), plus model-free shape-facts; all four are reported side by side, each framed as the plain-language question it answers. AICc is a displayed diagnostic, never a selection gate. Stage classification keys off the SIR R₀ posterior.

---

## 8. What we explicitly don't do

- **No causal claims.** We measure narrative dynamics; we don't claim narratives cause market moves or vice versa.
- **No trading or prediction outputs.** This is a descriptive measurement system.
- **No forecasting of narrative emergence.** We characterize narratives as they form; we don't predict what will emerge next.
- **No researcher-curated training data.** Every input is either a public document or a citation-anchored config value.
- **No "novel methodology".** Every analytical step uses an established technique with a citation. The novelty is in the combination and the application substrate (institutional macro discourse), not in any single component.
- **No financial press text in the embedding corpus.** We separately track press volume, but the embedded text is upstream-only.
- **No paywalled or closed-source data dependencies.** Everything in the core pipeline is publicly accessible and reproducible without institutional licenses.

---

## 9. Phase structure

The project runs through seven phases. We are currently in Phase 2 (corpus ingestion and lock-in) heading into Phase 4 (full-corpus anchor validation).

| Phase | What happens | Status |
|---|---|---|
| 0 | Scaffold, configs, anchor set, ingestors | Complete |
| 1 | Filtering, clustering, dynamics, validation pilot | Complete |
| 2 | Full corpus ingestion, methodology lock-in | In progress |
| 3 | Embedding + clustering at corpus scale | Initial run complete; re-run with locked methodology pending |
| 4 | Full-corpus anchor + fizzled validation (reported, not gated) | Blocked on Phase 2/3 completion |
| 5 | Streamlit dashboard, public deploy | Blocked on Phase 4 |
| 6 | Weekly cron update pipeline | Blocked on Phase 5 |
| 7 | Technical report, reproducibility audit | Final |

Each phase boundary is a methodology checkpoint — significant decisions get an Architecture Decision Record (ADR) in `docs/architecture_decisions.md` before code changes.

---

## 10. References (cited methodology anchors)

- **Embedding & retrieval**: Thakur et al. 2021 *BEIR* (NeurIPS); Reimers & Gurevych 2019 *SBERT*; Qwen3-Embedding-8B model card (ADR-036).
- **Clustering**: Grootendorst 2022 *BERTopic* (arXiv:2203.05794); McInnes et al. 2018 *UMAP*; McInnes & Healy 2017 *HDBSCAN*.
- **Published topic-model narrative studies**: Bybee, Kelly, Manela & Xiu 2024 (*Journal of Finance* 79(5), 3105-3147); Hansen, McMahon & Prat 2018 (*QJE*); Larsen & Thorsrud 2019 (*Journal of Econometrics* 210(1), 203-218); Larsen, Thorsrud & Zhulanova 2021 (*JME*); Bertsch, Hull, Lumsdaine & Zhang 2021 (*Economics Letters*).
- **Narrative-economics framing & related work**: Shiller 2017 (AEA Presidential Address); Shiller 2019 *Narrative Economics*; Roos & Reccius 2024 (*Journal of Economic Surveys*); Flynn & Sastry 2024 (NBER WP 32602); Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming *RES*).
- **Adjacent technical precedents**: Boutaleb, Picault & Grosjean 2024 *BERTrend* (ACL FuturED); Medeiros, Quigley & Revie 2026 (arXiv:2602.20939).
- **Text-as-data surveys**: Ash & Hansen 2023 (*Annual Review of Economics*); Gentzkow, Kelly & Taddy 2019 (*JEL*).
- **Epidemic / diffusion models**: Kermack & McKendrick 1927; Verhulst 1838; Bjørnstad 2018 *Epidemics: Models and Data using R*; Gelman et al. *Bayesian Data Analysis* 3rd ed.
- **Validation & statistics**: Brown & Warner 1985 (event-study windows); Benjamini & Hochberg 1995 (FDR); Efron & Tibshirani 1993 (bootstrap); Strehl & Ghosh 2002 (NMI quality measure); Jaccard 1901 (set similarity).
- **Deduplication**: Broder 1997 (MinHash); Henzinger 2006 (near-duplicate web pages).
- **LLM-frontier reference set** (positioning, not in active methodology): Schmidt et al. 2025; Hartley 2025; Gueta et al. 2025.
- **Taxonomy**: JEL Classification System, American Economic Association.

Full literature survey with overlap assessment and differentiation analysis is in `docs/related_work.md`.

Detailed methodology audit per parameter lives in the ADRs (`docs/architecture_decisions.md`), particularly ADR-015 / 016 / 018 (historical filter evolution), ADR-019 (comprehensive methodology lock-in: chunker, BERTopic, dynamics, validation), and **ADR-020 (basis-set corpus framing; pre-clustering JEL keyword filter removed; NBER restored; CFR dropped; CEA added; post-clustering JEL classifier introduced)**. ADR-020 is the canonical authority for source selection and filtering as of 2026-05-20.
