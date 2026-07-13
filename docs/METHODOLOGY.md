# bellwether — Methodology

How the system measures the lifecycle of macro-financial narratives, stage by stage. Every parameter is a published library default, a value cited from primary literature, or absent where no field-accepted anchor exists. The standing rules are in §5.

---

## 1. What the system measures

The system tracks how macro-financial narratives ("the Fed is engineering a soft landing", "inflation is transitory", "regional banks are at risk") form, spread, peak, and fade in U.S. policy discourse from 2010 to the present. For each narrative it produces a descriptive historical account: when it emerged, how fast it grew, when it peaked, how it decayed, and which past narratives it most resembles.

The frame is Robert Shiller's *Narrative Economics* (2017, 2019). Shiller argues that economic narratives spread through a population in patterns resembling epidemics, and leaves the measurement of that claim open. This system measures the lifecycle half of the framework. It tracks the volume of BERTopic clusters over time and reads each narrative's stage directly from its trajectory, with SIR, logistic, and Bass models fit alongside as interpretive lenses. Population-level virality and causal effects on macro outcomes are questions for structural work in the Flynn & Sastry (2024) tradition, and are out of scope here.

The discourse measured is institutional, policy, and academic writing: the upstream supply side of the narratives households later adopt. Andre, Haaland, Roth, Wiederholt & Wohlfart (2025, *Review of Economic Studies*, advance article) show that this layer differs qualitatively from narratives elicited from households.

Roos & Reccius (2024, *Journal of Economic Surveys*), the most recent survey of the field, finds no settled definition of an "economic narrative" and no operationalization of Shiller's framework beyond keyword counts. The closest quantitative precedents are Bybee, Kelly, Manela & Xiu (2024, *Journal of Finance*) and Larsen & Thorsrud (2019, *Journal of Econometrics*) on topic modeling, Bertsch et al. (2021, *Economics Letters*) on temporal dynamics, and Hansen, McMahon & Prat (2018, *QJE*) on institutional text. The full survey is in `docs/related_work.md`.

---

## 2. The lifecycle and its lenses

Each narrative's stage (emerging, growing, holding, or fading) is read directly from the recent shape of its weekly attention curve (Stage 8). Reading the stage from the curve itself keeps it well-defined for every trajectory, including the multi-wave and plateau shapes that no single growth model describes.

Three classical growth curves are fit alongside as interpretive lenses (Stage 7). The epidemic lens follows Shiller's analogy: a writer encounters a framing (susceptible), begins using it (infected), and later drops it (recovered), so the weekly volume of articles carrying a framing can trace the ignition, growth, peak, and decay of an outbreak. The SIR model (Kermack & McKendrick 1927) is fit through the Schlickeiser & Kröger (2020) closed-form solution of its equations, an exponential rise meeting a shifted sech² decay. It reports how fast the wave doubled on the way up, how fast it halved on the way down, and the ratio of the two. It does not report a reproduction number: R₀ = β/γ cannot be identified from a single attention curve without knowing the audience the narrative could have reached, so the lens reports only the rise and decay rates the curve itself measures (ADR-062). Epidemic models of idea diffusion have a long lineage: Goffman & Newill (1964) on the transmission of scientific ideas, Daley & Kendall (1965) on the canonical rumor model, and later work fitting SIR-type dynamics to news propagation, citation cascades, and online topic diffusion. The other two lenses are the logistic curve (Verhulst 1838) and the Bass adoption model (Bass 1969). All four readings are shown side by side. None is selected as a winner.

---

## 3. The pipeline

A document passes through eight stages.

### Stage 1 — Ingestion (basis set)

The corpus is a basis set: the smallest group of sources that spans every independent dimension of U.S. macro discourse, with no redundant or noise-dominated entries. Twelve active ingestors map to eight dimensions plus one cross-cutting register.

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

Each source covers a dimension no other source does. Where several sources share a dimension (the regional Feds on dimension 2, Brookings and PIIE on dimension 7), each covers a distinct sub-axis. Sources whose coverage duplicated another's were excluded. The main case is the Council on Foreign Relations: PIIE already covers its macro subset, and most of its remaining content is non-macro foreign policy. All sources are publicly accessible without a paid license.

These sources are where macro narratives form, among policymakers, researchers, and analysts. The financial press sits downstream and enters the analysis only as a volume signal (Stage 6). Its text is not ingested, for two reasons: premium analytical press is paywalled and cannot be bulk-licensed, and press text would tilt the corpus toward narratives that had already reached journalism, past the formation phase the system targets.

CBO publications are retrieved from the cbo.gov archive rather than the govinfo.gov CBO collection. The latter's GPO-deposit coverage falls from 41 records in 2010 to 6 in 2024, which would impose a time-varying selection filter on the CBO volume signal.

Ingestion is content-neutral: every article from every active source enters the corpus, with no topical filter before clustering.

### Stage 2 — Filtering

Two operations:

1. Restrict to publication dates in [2010-01-01, present].
2. Remove near-duplicates across the full corpus by MinHash over character 5-grams at a Jaccard threshold of 0.85 (Broder 1997; Henzinger 2006).

The basis-set source selection is the only macro-scope constraint applied at ingest. Topical relevance is assigned after clustering by the JEL classifier (Stage 5b), using the AEA's published taxonomy applied uniformly across sources.

### Stage 3 — Chunking

Documents shorter than 512 tokens pass through unchanged. Longer documents, such as FOMC minutes (~12,000 words), BIS Quarterly Review articles (~6,000 words), or IMF flagship chapters (~8,000 words), are split into 512-token chunks with ~64 tokens of overlap. A long document usually carries several distinct narratives (staff outlook, participants' inflation views, forward-guidance discussion), and chunking gives each its own embedding instead of averaging them into one vector. The 512-token unit follows the BEIR benchmark (Thakur et al. 2021, NeurIPS), which uses the first 512 word-pieces of every document across all its datasets.

### Stage 4 — Embedding

Each chunk is embedded with Qwen3-Embedding-8B, an open-source transformer that maps text to a 4,096-dimensional vector. Chunks about the same narrative lie close together in this space; chunks about different narratives lie far apart. The model leads the MTEB benchmark and carries an Apache 2.0 license. It accepts an instruction prefix: each chunk is prefixed with "Represent this financial policy document for narrative clustering", which biases the vector toward semantic content over writing style.

### Stage 5 — Clustering

BERTopic (Grootendorst 2022) performs topic discovery in three steps:

1. **UMAP** reduces the 4,096-dimensional vectors to 5 dimensions, preserving local neighborhood structure.
2. **HDBSCAN** finds dense regions in the reduced space. Each dense region is a cluster (a narrative); sparse points are outliers.
3. **c-TF-IDF** extracts each cluster's most distinguishing terms, which form its algorithmic name.

Every parameter is a BERTopic library default, and the clustering reports whatever structure emerges, at a single granularity: the level reported by published topic-model narrative studies (Bybee et al. 2024; Hansen et al. 2018; Larsen & Thorsrud 2019; Bertsch et al. 2021).

Each cluster's canonical identifier is its algorithmic name, its top 5–10 c-TF-IDF terms, e.g. `inflation, transitory, supply-chain, base-effects, Powell, FOMC`. An optional LLM-generated display label ("Transitory inflation debate, 2021") appears only in the interface and enters no calculation.

### Stage 5b — Post-clustering JEL classification

Each cluster is assigned a primary JEL code from the American Economic Association's Journal of Economic Literature classification (https://www.aeaweb.org/econlit/jelCodes.php):

1. Represent the cluster by its centroid, the mean of its chunk embeddings in the Qwen3 space used for clustering.
2. Embed the AEA's verbatim published description of each top-level JEL code (A–Z) in the same space.
3. Assign the code whose description is the nearest cosine neighbor of the centroid.

The JEL code is a display flag, and every non-noise cluster proceeds to dynamics fitting (Stages 6–8) regardless of it. Clusters whose primary code falls in the macro-finance scope, E (macroeconomics and monetary), F (international), G (financial), or H (public economics, including fiscal H6), are marked in-scope. The rest keep their JEL label and are fit, staged, and shown alongside them.

The taxonomy is external and unedited; the AEA maintains it and uses it to classify journal submissions. Classifying after clustering means each assignment draws on cluster-level content (typically 100–1,000 documents averaged into the centroid) rather than a single article's title and body, and keeps the embedding and clustering steps independent of any topic taxonomy.

The classifier reports a `runner_up_gap` per cluster, the cosine-similarity margin between its primary and second-best code. A median below 0.05 across clusters would indicate ambiguous assignment. The diagnostic ships with the classifier output.

### Stage 6 — Volume signals (institutional and press)

Each narrative cluster yields two weekly volume series.

- **Institutional volume** — articles in the cluster per week. This is the primary signal and the curve the dynamics models are fit to.
- **Press volume** — weekly story counts from the Media Cloud API against its broad U.S. national news collection, queried by the cluster's top c-TF-IDF terms joined with Boolean OR.

The two series support cross-validation and lead-lag reading. A narrative present in both institutional discourse and the press is corroborated. Institutional volume without press volume marks a procedural artifact. Press volume without institutional discourse is downstream of the corpus and out of scope. Institutional discourse typically leads the press by days to weeks, and plotting both on one axis shows the offset.

Media Cloud is a volume signal only; its text never enters embedding or clustering. The institutional series is smoothed with a 7-day centered moving average to remove the weekend drop in daily output (Shumway & Stoffer); the press series is shown as reported. Media Cloud's news archive thins before roughly 2017, so early press counts may be sparse or absent, and the artifact carries this caveat for display.

A market series (the VIX, from FRED) joins the press counts as a second external overlay. Both support a lead-lag reading: bidirectional Granger tests (Granger 1969) on the first-differenced weekly pairs sweep lags of one to four weeks in each direction and report the most significant lag. This is a statement about temporal precedence, not about cause. On the site's charts each overlay is min-max rescaled onto the narrative's volume axis (its own minimum at the floor, its own maximum at the tallest bar), so an overlay shows timing and shape but its height carries no level information. The Granger tests run on the unscaled weekly series. Neither overlay feeds embedding, clustering, or the dynamics fits.

### Stage 7 — Dynamics fitting

Each non-noise cluster is fit on its **active lifecycle**: the central 95% of its cumulative attention mass. The trim drops the sparse leading and trailing stragglers (a stray article years before or after the narrative's active life) that would otherwise stretch nearly every fit window across the full corpus, while keeping every wave that carries real attention, so multi-wave narratives are fit over all their humps. It reuses the α = 0.05 already used for the trend test. Staging and the displayed volume series stay on the full span (ADR-060). On that window the cluster is fit by four lenses, reported side by side:

- **Logistic curve** (Verhulst 1838) — S-shaped growth to saturation; carrying capacity *L*, growth rate *k*, midpoint *t₀*.
- **SIR model** (Kermack & McKendrick 1927), fit via the Schlickeiser & Kröger (2020) closed-form prevalence — an exponential rise meeting a shifted sech² decay. Reports the rise rate (doubling time up), decay rate (half-life down), and their asymmetry. No R₀ (not identifiable from one curve; ADR-062).
- **Bass diffusion** (Bass 1969) — separates external and internal influence on adoption; reports total reach *m*, innovation *p*, and imitation *q*.
- **Model-free shape facts** — peak height and date, time to peak, active span, and wave count, read directly off the curve.

The three model lenses are fit by bounded nonlinear least-squares (`scipy.least_squares`), seeded from data-scaled initial values: the SIR from the observed peak and span, the Bass from the Sultan, Farley & Lehmann (1990) meta-analysis means over 213 diffusion studies (p ≈ 0.03 innovation, q ≈ 0.38 imitation). Every reported number is a direct property of the fitted curve; none rests on an unobservable population size or on borrowed epidemiological constants. A fit-quality gate keeps or flags each lens: a lens is shown where the optimizer converges and its R² clears a fixed floor, and marked "no fit" otherwise. In practice SIR and Bass appear on bump-shaped narratives, while the logistic grays out on the rise-and-fall shapes a monotone S-curve cannot describe. AICc is displayed with each fit as a diagnostic and selects no model.

### Stage 8 — Stage classification

Lifecycle stage is read from the trajectory of the smoothed volume series, independent of any fitted model. The recent trend is tested with the modified Mann–Kendall test (Mann 1945; Kendall 1948), using the Hamed & Rao (1998) variance correction for the serial correlation that smoothing introduces; magnitude comes from a Theil–Sen slope (Sen 1968) on log-volume. A narrative with no significant trend is split by where its recent window sits relative to its own historical **peak**, the highest-volume equal-width window in its history (ADR-058). This yields four mutually exclusive states:

- **Growth** — a significant rising trend (Mann–Kendall *p* < α, positive slope).
- **Decay** — a significant falling trend (Mann–Kendall *p* < α, negative slope).
- **Stable** — no significant trend, with recent volume at or above a quarter of the peak-window level: a high plateau.
- **Dormant** — no significant trend, with recent volume under a quarter of the peak-window level: faded. A narrative too short to resolve a separate peak window is treated as not faded.

The trend threshold is α = 0.05 and the dormancy line is a quarter of the narrative's own peak; both are fixed values, not swept. Splitting no-trend narratives by level against their own peak, rather than against their quietest window, keeps the faded/plateau distinction from collapsing under the low but persistent institutional tail every narrative carries (ADR-058). Wallinga & Lipsitch (2007) supply the epidemiological grounding: the sign of the recent growth rate is the sign of R_t − 1, so a rising series is spreading whether or not a clean SIR fit exists.

The recent window is the tail of each narrative's own series, so the trend describes its final chapter wherever that fell in time. A narrative that stopped while still rising would otherwise read *growth* indefinitely. A staleness override corrects this: a narrative whose last activity trails the corpus frontier by more than 16 weeks (a quarter, matching the heating horizon below) reads *dormant* regardless of trend shape, so the stage the site presents as "where it sits now" is honest to the calendar (ADR-075). The underlying trend is retained in the narrative's detail record. *Decay* stays a defined state for a genuine sharp mid-collapse, but it is rare to absent on this corpus: institutional narratives typically stop rather than decline gradually — a fall shows up as absence, and zeros carry no rank signal for a Mann–Kendall test — so a faded narrative lands in *dormant* rather than passing through a visible *decay*.

"Newly emerging" is a separate recency flag on top of the four states: a narrative whose onset falls within the trailing four weeks of the corpus is flagged emerging regardless of its stage, so a narrative arriving at the corpus frontier is surfaced even before its short history registers a significant trend (ADR-059).

In practice the onset flag almost never fires on surfaced narratives, and the reason is structural rather than a defect: clusters in this corpus are long-lived narrative families, and new events are absorbed into existing families (institutional writing on the 2026 Iran war joins sanctions clusters whose onsets date to 2010) rather than founding new clusters that could clear the article floor quickly. The display layer therefore carries a complementary *corpus heating* signal (ADR-074): a narrative heats when its mean weekly article count over the trailing 16 weeks sits at least 2 standard errors above its own trailing 52-week baseline, with at least 3 articles in the window. This mirrors the press-heating signal in shape — a recent window judged against the narrative's own yearly baseline — but scales the deviation by √16 (the standard error of the windowed mean), since institutional volume is single-digit weekly counts and a windowed mean cannot clear two raw weekly deviations. The signal is computed for surfaced narratives from their published volume series and baked into the cluster directory for sub-floor clusters; like press heating it is display-only and never feeds the filter, the embedding, the clustering, or the fits.

---

## 4. Similar past narratives

For each narrative, the tool surfaces the most similar past narratives from the full historical set by three measures.

| Measure | Captures | Method |
|---|---|---|
| **Semantic** | same topic | cosine similarity between cluster embedding centroids |
| **Lexical** | same vocabulary | Jaccard overlap on top-K c-TF-IDF terms |
| **Morphological** | same spread pattern | Pearson correlation on normalized weekly volume curves |

Each measure returns its own top-5 ranking. The measures are complementary: morphological similarity can link narratives that share an epidemic shape without sharing vocabulary, such as the 2022 inflation peak and a 2008 commodity-price spike.

---

## 5. Methodological principles

The rules below govern every parameter choice.

1. **Anchored or removed.** Each value is a published library default (cited), a primary-literature value (cited), or absent because no field-accepted anchor exists.
2. **Single field-accepted values.** Each parameter is fixed at one field-accepted value; the pipeline runs no sensitivity sweeps.
3. **Reported, not gated.** Diagnostics — clustering NMI, fit R², AICc — are reported for the reader to judge; none is a pass/fail gate.
4. **Scope assigned after clustering, never gated.** The post-clustering JEL classifier (`jel_classifier.py`) assigns each cluster to its nearest AEA prototype; the resulting code is a per-narrative display flag, so clusters outside {E, F, G, H} are labeled rather than dropped. The only ingest-time filters are the 2010-present window and URL/content dedup.
5. **Single clustering granularity.** The pipeline reports BERTopic's default output without hierarchical merging.
6. **Field-standard taxonomies.** The JEL classification anchors topical scope; the BEIR convention anchors chunk size; BERTopic defaults anchor the clustering.
7. **Abandoned components are deleted.** Retired ingestors, code paths, and configuration are removed from the pipeline, not retained inactive.
8. **Full corpus, no split, no pre-registration.** No parameter is tuned, so there is no train-fitted quantity for a held-out boundary to test; the pipeline runs over the full 2010-present corpus without a temporal split or a registered analysis plan. Credibility rests on principles 1–7.
9. **Four dynamics lenses, model-free staging.** Every non-noise cluster is fit by the logistic, SIR, and Bass models alongside model-free shape facts, reported side by side as interpretive lenses. Lifecycle stage is read directly from the volume trajectory (Stage 8) and does not depend on any fitted model.

---

## 6. References (cited methodology anchors)

- **Embedding & retrieval**: Thakur et al. 2021 *BEIR* (NeurIPS); Qwen3-Embedding-8B model card.
- **Clustering**: Grootendorst 2022 *BERTopic* (arXiv:2203.05794); McInnes et al. 2018 *UMAP*; McInnes & Healy 2017 *HDBSCAN*.
- **Published topic-model narrative studies**: Bybee, Kelly, Manela & Xiu 2024 (*Journal of Finance* 79(5), 3105–3147); Hansen, McMahon & Prat 2018 (*QJE* 133(2), 801–870); Larsen & Thorsrud 2019 (*Journal of Econometrics* 210(1), 203–218); Bertsch, Hull, Lumsdaine & Zhang 2021 (*Economics Letters*).
- **Narrative-economics framing**: Shiller 2017 (AEA Presidential Address); Shiller 2019 *Narrative Economics*; Roos & Reccius 2024 (*Journal of Economic Surveys*); Flynn & Sastry 2024 (NBER WP 32602); Andre, Haaland, Roth, Wiederholt & Wohlfart (2025, *RES*, advance article).
- **Epidemic / diffusion models**: Kermack & McKendrick 1927; Schlickeiser & Kröger 2020 (closed-form SIR solution, *J. Phys. A* 53:505601); Verhulst 1838 (logistic); Bass 1969 (diffusion of innovations); Sultan, Farley & Lehmann 1990 (Bass meta-analysis).
- **Epidemic models of idea spread**: Goffman & Newill 1964 (*Nature*); Daley & Kendall 1965 (*Nature*, rumor model).
- **Lead-lag testing**: Granger 1969 — markets-vs-narrative timing overlay.
- **Trend & stage classification**: Mann 1945, Kendall 1948 (rank trend test); Hamed & Rao 1998 (autocorrelation variance correction); Sen 1968 (Theil–Sen slope); Wallinga & Lipsitch 2007 (growth-rate ↔ R_t correspondence).
- **Time-series smoothing**: Shumway & Stoffer 2017, *Time Series Analysis and Its Applications* (4th ed., Springer) — moving-average convention for the weekly series.
- **Similarity & clustering metrics**: Strehl & Ghosh 2002 (NMI); Jaccard 1901 (set similarity).
- **Deduplication**: Broder 1997 (MinHash); Henzinger 2006 (near-duplicate web pages).
- **Taxonomy**: JEL Classification System, American Economic Association.

The full literature survey, with overlap assessment and differentiation, is in `docs/related_work.md`.
