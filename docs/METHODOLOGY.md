# Macro Narrative Dynamics — Methodology

How the system measures the lifecycle of macro-financial narratives, stage by stage, with the field-accepted citation behind each choice. Every parameter is a published library default, a value cited from primary literature, or absent where no field-accepted anchor exists; the standing rules are in §6.

---

## 1. What the system measures

The system measures how macro-financial narratives — "the Fed is engineering a soft landing", "inflation is transitory", "regional banks are at risk" — form, spread, peak, and fade in U.S. policy discourse from 2010 to the present. Its output is a descriptive, historical account of each narrative's lifecycle: emergence, growth rate, peak, and decay, together with the past narratives a current one most resembles.

The frame is Robert Shiller's *Narrative Economics* (2017, 2019), which holds that economic narratives spread through a population in patterns resembling epidemics and leaves the formal measurement of that claim open. The system operationalizes the lifecycle half of that framework — emergence, growth, peak, decay — by fitting SIR and logistic models to the volume of BERTopic clusters. Population-level virality and causal effects on macro outcomes belong to structural work in the Flynn & Sastry (2024) tradition.

The discourse measured here — institutional, policy, and academic writing — is the upstream supply side of the narratives households later adopt, a layer that Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming, *Review of Economic Studies*) show to differ qualitatively from household-elicited narratives.

Roos & Reccius (2024, *Journal of Economic Surveys*), the most recent survey of narrative economics, describes a field still consolidating, with no settled definition of an "economic narrative" and no operationalization of Shiller's framework beyond keyword counts. The closest quantitative precedents are Bybee, Kelly, Manela & Xiu (2024, *Journal of Finance*) and Larsen & Thorsrud (2019, *Journal of Econometrics*) on topic modeling, Bertsch et al. (2021, *Economics Letters*) on temporal dynamics, and Hansen, McMahon & Prat (2018, *QJE*) on institutional text. The full survey is in `docs/related_work.md`.

---

## 2. The epidemic analogy

A narrative spreads from writer to writer as a contagion spreads through a population: a writer encounters a framing (susceptible), begins using it (infected), and later drops it (recovered). Aggregated over many writers, the weekly volume of articles carrying a framing traces a curve with the shape of an epidemic — ignition, exponential growth, peak, decay.

The SIR model (Kermack & McKendrick 1927) — Susceptible, Infected, and Recovered populations governed by a transmission rate β and a recovery rate γ — fits these volume curves with the machinery it applies to disease incidence. The basic reproduction number R₀ = β/γ carries the same meaning: above 1 the narrative spreads, below 1 it fades.

Epidemic models of idea diffusion have an established lineage. Goffman & Newill (1964) modeled the transmission of scientific ideas as an epidemic; Daley & Kendall (1965) built the canonical rumor model on SIR mechanics; and a later literature fits SIR-type dynamics to news propagation, citation cascades, and online topic diffusion. The substrate here is multi-source institutional macro discourse, reported through a public tool.

---

## 3. The pipeline

A document passes through eight stages.

### Stage 1 — Ingestion (basis set)

The corpus is a basis set: the minimal group of sources spanning every independent dimension of U.S. macro discourse, with no redundant or noise-dominated entries. Twelve active ingestors map to eight dimensions plus one cross-cutting register.

| Dimension | Source(s) |
|---|---|
| 1. U.S. monetary authority | Federal Reserve Board (FOMC, speeches including Jackson Hole, Beige Book, FEDS Notes, Monetary Policy Report, Financial Stability Report) |
| 2. U.S. monetary research | Regional Feds — New York (Liberty Street, Staff Reports), San Francisco (Economic Letter, Working Papers, FedViews, Beige Book, Community Development; cross-posts excluded), Chicago (multiple series including president speeches and the CFSBC/CFSEC conditions surveys), Atlanta (macroblog, working papers) |
| 3. International macro authority | IMF (WEO, GFSR, Finance & Development, working papers, blog) |
| 4. International central-bank network | BIS (Quarterly Review, working papers, Bulletins, curated central-bank speeches) |
| 5. U.S. fiscal authority | CBO (legislative scoring, outlook, working papers, Monthly Budget Review) and CEA (Economic Report of the President, via govinfo.gov) |
| 6. U.S. financial-stability research | Treasury OFR (working papers, FSOC reports) |
| 7. U.S. policy think tank | Brookings (Economic Studies, Hutchins Center) and PIIE (international policy) |
| 8. Academic primary work and column | NBER (working papers) and VoxEU (CEPR columns) |
| Cross-cutting Q&A register | Congressional Treasury Secretary testimony |

Each source spans a dimension no other source covers. Where several sources share a dimension — the regional Feds on dimension 2, Brookings and PIIE on dimension 7 — each covers a distinct sub-axis. A source whose coverage duplicated another's was excluded; the Council on Foreign Relations, whose macro subset PIIE already covers and whose content is largely non-macro foreign policy, is the main such case. All sources are publicly accessible and retrievable without a paid license.

These sources are where macro narratives form — among policymakers, researchers, and analysts — ahead of the financial press, which sits downstream. The financial press enters the analysis as a separate volume signal (Stage 6) rather than as embedded text: premium analytical press is paywalled and not bulk-licensable, and ingesting press text would bias the corpus toward narratives that had already reached journalism, past the formation phase the system targets.

CBO publications are retrieved from the cbo.gov archive directly rather than from the govinfo.gov CBO collection, whose GPO-deposit coverage falls from 41 records in 2010 to 6 in 2024 and would impose a time-varying selection filter on the CBO volume signal.

Ingestion is content-neutral: every article from every active source enters the corpus regardless of topic, with no topical filter before clustering.

### Stage 2 — Filtering

Two operations:

1. Restrict to publication dates in [2010-01-01, present].
2. Remove near-duplicates across the full corpus by MinHash over character 5-grams at a Jaccard threshold of 0.85 (Broder 1997; Henzinger 2006).

The basis-set source selection is the only macro-scope constraint applied at ingest. Topical relevance is assigned after clustering by the JEL classifier (Stage 5b), using the AEA's published taxonomy applied uniformly across sources.

### Stage 3 — Chunking

Documents shorter than 512 tokens pass through unchanged. Longer documents — FOMC minutes (~12,000 words), BIS Quarterly Review articles (~6,000 words), IMF flagship chapters (~8,000 words) — are split into 512-token chunks with ~64-token overlap. A long document carries several distinct narratives — staff outlook, participants' inflation views, forward-guidance discussion — and chunking gives each its own embedding instead of averaging them into one vector. The 512-token unit follows the BEIR benchmark (Thakur et al. 2021, NeurIPS), which uses the first 512 word-pieces of every document across all its datasets.

### Stage 4 — Embedding

Each chunk is embedded with Qwen3-Embedding-8B, an open-source transformer that maps text to a 4,096-dimensional vector. Chunks about the same narrative lie close together in this space; chunks about different narratives lie far apart. The model leads the MTEB benchmark and carries an Apache 2.0 license. It is instruction-aware: each chunk is prefixed with "Represent this financial policy document for narrative clustering" to bias the vector toward semantic content over writing style.

### Stage 5 — Clustering

BERTopic (Grootendorst 2022) performs transformer-based topic discovery in three steps:

1. **UMAP** reduces the 4,096-dimensional vectors to 5 dimensions, preserving local neighborhood structure.
2. **HDBSCAN** finds dense regions in the reduced space; each dense region is a cluster (a narrative), and sparse points are outliers.
3. **c-TF-IDF** extracts each cluster's most distinguishing terms, which form its algorithmic name.

Every parameter is a BERTopic library default (Grootendorst 2022), and the clustering reports whatever structure emerges, at a single granularity — the level reported by published topic-model narrative studies (Bybee et al. 2024; Hansen et al. 2018; Larsen & Thorsrud 2019; Bertsch et al. 2021).

Each cluster carries an algorithmic name — its top 5–10 c-TF-IDF terms, e.g. `inflation, transitory, supply-chain, base-effects, Powell, FOMC` — which is the canonical identifier used in all queries and analysis. An optional LLM-generated display label ("Transitory inflation debate, 2021") appears only in the interface and enters no calculation.

### Stage 5b — Post-clustering JEL classification

Each cluster is assigned a primary JEL code from the American Economic Association's Journal of Economic Literature classification (https://www.aeaweb.org/econlit/jelCodes.php):

1. Take the cluster's top c-TF-IDF terms.
2. For each top-level JEL code (A–Z), take the AEA's verbatim published description.
3. Embed the cluster terms and the JEL descriptions in the same Qwen3 space used for clustering.
4. Assign the JEL code whose description is the nearest cosine neighbor.

Every non-noise cluster proceeds to dynamics fitting (Stages 6–8); the JEL code is a per-narrative display flag, not a gate. Clusters whose primary code falls in the macro-finance scope — E (macroeconomics and monetary), F (international), G (financial), H (public economics, including fiscal H6) — are marked in-scope. Clusters outside that scope carry their JEL label rather than being dropped, and are fit, staged, and shown alongside the rest.

The taxonomy is external and unedited: the AEA maintains it and uses it to classify journal submissions. The classifier embeds the AEA's own descriptions and assigns by cosine similarity — the operation that produced the clusters — with no intermediate keyword choices. The {E, F, G, H} scope is the standard macro-finance mapping. Running the classifier after clustering uses cluster-level content (typically 100–1,000 documents and their c-TF-IDF terms), which carries more signal than a single article's title and body, and keeps the embedding and clustering steps independent of any topic taxonomy.

The classifier reports a `runner_up_gap` per cluster — the cosine-similarity difference between its primary and second-best JEL code; a median below 0.05 across clusters would indicate ambiguous assignment. The diagnostic ships with the classifier output.

### Stage 6 — Volume signals (institutional and press)

Each narrative cluster yields two weekly volume series.

- **Institutional volume** — articles in the cluster per week; the primary signal and the curve the dynamics models are fit to.
- **Press volume** — weekly story counts from the Media Cloud API against its broad U.S. national news collection, queried by the cluster's top c-TF-IDF terms joined with Boolean OR.

The two series support cross-validation and lead-lag reading. A narrative present in both institutional discourse and the press is corroborated across both; institutional volume without press volume marks a procedural artifact; press volume without institutional discourse is downstream of the corpus and outside scope. Institutional discourse typically leads the press by days to weeks, and plotting both on one axis shows the offset directly.

Media Cloud is a volume signal only; its text never enters embedding or clustering. The institutional series is smoothed with a 7-day centered moving average to remove the weekend drop in daily output (Shumway & Stoffer); the press series is shown as reported.

### Stage 7 — Dynamics fitting

Each non-noise cluster is fit on its smoothed weekly institutional curve by four lenses, reported side by side:

- **Logistic curve** (Verhulst 1838) — S-shaped growth to saturation; carrying capacity *L*, growth rate *k*, midpoint *t₀*.
- **SIR model** (Kermack & McKendrick 1927) — Susceptible, Infected, and Recovered compartments with transmission rate β and recovery rate γ, giving R₀ = β/γ (R₀ > 1 spreading, R₀ < 1 fading).
- **Bass diffusion** (Bass 1969) — separating external and internal influence on adoption.
- **Model-free shape facts** — peak height and date, time to peak, active span, and wave count, read directly off the curve.

The parametric fits use Bayesian inference (PyMC) with weakly-informative priors from the epidemic-modeling literature (Bjørnstad 2018; Gelman et al., *BDA3*), and report the full posterior over R₀ rather than a point estimate. AICc accompanies each fit as a displayed diagnostic and selects no model.

### Stage 8 — Stage classification

Each fitted narrative receives one of three lifecycle stages from the SIR R₀ posterior:

- **Growth** — R₀ ≥ 1; spreading.
- **Decay** — R₀ < 1; fading.
- **Dormant** — the fit did not produce a usable R₀ (no convergence, or none returned).

The R₀ = 1 boundary is the classical epidemic threshold (Kermack & McKendrick 1927). "Newly emerging" is a separate dashboard recency filter — narratives active within the trailing four weeks — and does not enter stage classification.

---

## 4. Validation against anchor narratives

A fixed set of ten anchor narratives spans 2010–2023, each with a documented ignition date and primary-source citation: SVB collapse (2023-03-09), COVID market crash (2020-02-24), Brexit aftermath (2016-06-24), the transitory-inflation debate (2021-Q2), Credit Suisse stress (2023-03-15), regional banking contagion (2023-03-13), the 2022 inflation peak (Q2–Q3), soft-landing emergence (2023-Q3–Q4), the 2013 taper tantrum (2013-05-22), and the 2015 China devaluation scare (2015-08-11).

For each anchor, validation collects the articles published within ±14 days of the documented ignition date — the event-study window of Brown & Warner (1985) — and records whether at least half of them land in a single non-noise cluster. The recovery rate is reported per anchor and in aggregate as a face-validity diagnostic; no pass/fail threshold is applied to it, and it never informs the filter, the embedding, the clustering, or any hyperparameter.

---

## 5. Similar past narratives

For each narrative, the tool surfaces the most similar past narratives from the full historical set by three measures.

| Measure | Captures | Method |
|---|---|---|
| **Semantic** | same topic | cosine similarity between cluster embedding centroids |
| **Lexical** | same vocabulary | Jaccard overlap on top-K c-TF-IDF terms |
| **Morphological** | same spread pattern | Pearson correlation on normalized weekly volume curves |

Each measure returns its own top-5 ranking. The measures are complementary: morphological similarity can link narratives that share an epidemic shape without sharing vocabulary, such as the 2022 inflation peak and a 2008 commodity-price spike.

---

## 6. Methodological principles

The rules below govern every parameter choice.

1. **Anchored or removed.** Each value is a published library default (cited), a primary-literature value (cited), or absent because no field-accepted anchor exists.
2. **Single field-accepted values.** Each parameter is fixed at one field-accepted value; the pipeline runs no sensitivity sweeps.
3. **Reported, not gated.** Diagnostics — anchor recovery rate, clustering NMI, fit R², R₀ interval width, AICc — are reported for the reader to judge; none is a pass/fail gate.
4. **Scope assigned after clustering, never gated.** The post-clustering JEL classifier (`jel_classifier.py`) assigns each cluster to its nearest AEA prototype; the resulting code is a per-narrative display flag, so clusters outside {E, F, G, H} are labeled rather than dropped. The only ingest-time filters are the 2010-present window and URL/content dedup.
5. **Single clustering granularity.** The pipeline reports BERTopic's default output without hierarchical merging.
6. **Anchors validate only.** They never influence the filter, the embedding, the clustering, or any hyperparameter.
7. **Field-standard taxonomies.** The JEL classification anchors topical scope; the BEIR convention anchors chunk size; BERTopic defaults anchor the clustering.
8. **Abandoned components are deleted.** Retired ingestors, code paths, and configuration are removed from the pipeline, not retained inactive.
9. **Full corpus, no split, no pre-registration.** No parameter is tuned, and none is tuned toward anchor recovery, so there is no train-fitted quantity for a held-out boundary to test; the pipeline runs over the full 2010-present corpus without a temporal split or a registered analysis plan. Credibility rests on principles 1–8.
10. **Four dynamics lenses.** Every non-noise cluster is fit by the logistic, SIR, and Bass models alongside model-free shape facts, reported side by side; stage classification keys off the SIR R₀ posterior.

---

## 7. References (cited methodology anchors)

- **Embedding & retrieval**: Thakur et al. 2021 *BEIR* (NeurIPS); Reimers & Gurevych 2019 *SBERT*; Qwen3-Embedding-8B model card.
- **Clustering**: Grootendorst 2022 *BERTopic* (arXiv:2203.05794); McInnes et al. 2018 *UMAP*; McInnes & Healy 2017 *HDBSCAN*.
- **Published topic-model narrative studies**: Bybee, Kelly, Manela & Xiu 2024 (*Journal of Finance* 79(5), 3105–3147); Hansen, McMahon & Prat 2018 (*QJE* 133(2), 801–870); Larsen & Thorsrud 2019 (*Journal of Econometrics* 210(1), 203–218); Larsen, Thorsrud & Zhulanova 2021 (*JME*); Bertsch, Hull, Lumsdaine & Zhang 2021 (*Economics Letters*).
- **Narrative-economics framing & related work**: Shiller 2017 (AEA Presidential Address); Shiller 2019 *Narrative Economics*; Roos & Reccius 2024 (*Journal of Economic Surveys*); Flynn & Sastry 2024 (NBER WP 32602); Andre, Haaland, Roth, Wiederholt & Wohlfart (forthcoming, *RES*).
- **Adjacent technical precedents**: Boutaleb, Picault & Grosjean 2024 *BERTrend* (ACL FuturED); Medeiros, Quigley & Revie 2026 (arXiv:2602.20939).
- **Text-as-data surveys**: Ash & Hansen 2023 (*Annual Review of Economics*); Gentzkow, Kelly & Taddy 2019 (*JEL* 57(3), 535–574).
- **Epidemic / diffusion models**: Kermack & McKendrick 1927; Verhulst 1838 (logistic); Bass 1969 (diffusion of innovations); Bjørnstad 2018 *Epidemics: Models and Data using R*; Gelman et al. *Bayesian Data Analysis* 3rd ed.
- **Epidemic models of idea/information spread**: Goffman & Newill 1964 (*Nature*); Daley & Kendall 1965 (*Nature*, rumor model); Rogers 2003 *Diffusion of Innovations* 5th ed.
- **Lead-lag testing**: Granger 1969 — markets-vs-narrative timing overlay.
- **Validation & statistics**: Brown & Warner 1985 (event-study windows); Benjamini & Hochberg 1995 (FDR); Efron & Tibshirani 1993 (bootstrap); Strehl & Ghosh 2002 (NMI); Jaccard 1901 (set similarity).
- **Deduplication**: Broder 1997 (MinHash); Henzinger 2006 (near-duplicate web pages).
- **Related LLM-based work (positioning)**: Schmidt et al. 2025; Hartley 2025; Gueta et al. 2025.
- **Taxonomy**: JEL Classification System, American Economic Association.

The full literature survey, with overlap assessment and differentiation, is in `docs/related_work.md`.
