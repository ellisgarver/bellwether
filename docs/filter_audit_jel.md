# Filter audit — JEL E/F/G/H standardization

Audit of the corpus topic filter, mapping current keyword categories to the
JEL (Journal of Economic Literature) Classification System maintained by the
American Economic Association. The JEL taxonomy is the field-standard
classification for economics research; anchoring the filter to JEL subcodes
makes the operational definition of "macro narrative content" pre-registration
defensible and replication-friendly.

**Status:** draft, written 2026-05-18 during Phase 2 closeout. Ratification is
gated on a new ADR (proposed ADR-015 in `architecture_decisions.md`).

---

## Current filtering architecture (two stages)

**Stage 1 — Per-source inline filter (institutional.py).** Runs at ingest time.
Each affected ingestor has its own bespoke keyword list, applied to the article
title before the page body is fetched. Sources with inline filters: CBO, NBER,
VoxEU, Brookings, CFR, Congressional. Sources without: IMF, Fed
(FederalReserveIngestor), BIS, Treasury, OFR, fed_regional, PIIE.

**Stage 2 — Canonical filter (`src/mnd/filtering/topic_filter.py`).** Runs at
the `filter` pipeline step. Loads keywords from
`config/topic_filter_keywords.yaml` (228 lines, 12 categories) and applies a
two-gate test: ≥2 keyword matches AND embedding-similarity vs.
`data/anchors/topic_seed_articles.jsonl`. Both gates required (AND, not OR).

**The methodology problem:** the Stage 1 inline lists are researcher-derived,
ad-hoc per source, and not the same list across sources. Stage 1 is not a
subset of Stage 2 — it can drop articles that Stage 2 would have admitted.
This means **the corpus is shaped by per-source researcher judgment that is
not pre-registered and not audit-traceable.**

---

## JEL subcodes in scope for this study

The project's stated scope is "U.S. macro-financial media discourse." That maps
cleanly to four JEL top-level codes:

### E — Macroeconomics and Monetary Economics

- **E2** Consumption, Saving, Production, Investment, Labor Markets — household
  consumption, wages, employment
- **E3** Prices, Business Fluctuations, and Cycles — inflation, deflation,
  recession, business cycle
- **E4** Money and Interest Rates — interest rate channel, monetary aggregates
- **E5** Monetary Policy, Central Banking, and the Supply of Money and Credit
  — FOMC, central bank operations, QE/QT
- **E6** Macroeconomic Policy, Macroeconomic Aspects of Public Finance, and
  General Outlook — fiscal-monetary mix, outlook surveys
- **E7** Macro-Based Behavioral Economics — narrative economics, expectations

### F — International Economics

- **F1** Trade — tariffs, trade balance
- **F3** International Finance — capital flows, exchange rate management
- **F4** Macroeconomic Aspects of International Trade and Finance — global
  imbalances, sudden stops
- **F5** International Relations, National Security, IPE — sanctions, currency
  wars, geopolitical risk
- **F6** Economic Impacts of Globalization — deglobalization, reshoring

### G — Financial Economics

- **G1** General Financial Markets — equity, bond, derivatives market dynamics
- **G2** Financial Institutions and Services — banks, insurance, asset managers
- **G3** Corporate Finance and Governance — capital structure, restructuring
  (mostly out of scope for macro narratives, included only where macro-relevant)

### H — Public Economics (selected)

- **H6** National Budget, Deficit, and Debt — debt ceiling, sovereign debt,
  Treasury issuance

Other JEL codes (D Microeconomics, I Health Education, J Labor general, L
Industrial Organization, Q Agriculture/Environment, R Urban/Regional) are out
of scope unless they intersect E/F/G/H (e.g., Q4 Energy → oil price shocks
are E3/F4-relevant).

---

## Audit: current YAML categories vs. JEL coverage

For each of the 12 categories in `config/topic_filter_keywords.yaml`, the
table below lists the JEL subcode(s) the category operationalizes and notes
any gaps relative to that subcode.

| YAML Category | Primary JEL | Coverage assessment | Recommended additions |
|---|---|---|---|
| `core_macro` | E2, E3, E31 (Price Level), E32 (Business Fluctuations) | Solid coverage of inflation/recession terminology | Add: `core PCE`, `supercore inflation`, `unit labor costs`, `output gap` |
| `monetary_policy` | E5, E52 (Monetary Policy), E58 (Central Banks) | Strong on Fed/ECB/BOJ/BoE/PBOC; covers operating tools | Add: `r-star`, `neutral rate`, `dot plot`, `forward guidance` (already in `macro_themes` — consolidate), `IORB`, `interest on reserves`, `repo facility`, `standing repo` |
| `rates_and_bonds` | E43 (Interest Rates), G12 (Asset Pricing) | Good on yield curve, TIPS, term structure | Add: `term spread`, `5y5y forward`, `inflation breakevens` (modernize from `breakeven inflation`), `bond rally`, `bond selloff` |
| `credit` | G2 (Financial Institutions), G33 (Bankruptcy) | Covers spread/quality/default; thin on credit cycle drivers | Add: `lending standards`, `senior loan officer`, `SLOOS`, `commercial real estate`, `CRE`, `private credit` |
| `banking_and_financial_stability` | G21 (Banks), G28 (Regulation) | Strong post-2008 vocabulary | Add: `BTFP`, `Bank Term Funding Program`, `liquidity coverage ratio`, `LCR`, `held-to-maturity`, `HTM`, `unrealized losses` |
| `currency` | F31 (Foreign Exchange), F33 (International Monetary Arrangements) | Covers FX dynamics and crisis vocabulary | Add: `carry trade`, `dollar funding`, `swap lines`, `FX intervention` |
| `markets` | G1, G11, G14 (Information & Market Efficiency) | Index/regime coverage solid | Add: `risk-on`, `risk-off`, `safe haven`, `correlation breakdown`, `financial conditions index`, `FCI`, `Goldman financial conditions` |
| `macro_themes` | E32, E37 (Forecasting), F62 (Globalization) | Captures named narratives well | Move `forward guidance` here from `monetary_policy` for consistency. Add: `Goldilocks`, `disinflationary boom`, `K-shaped recovery`, `excess savings` |
| `shocks_and_geopolitics_macro` | F51, F13 (Trade Policy), Q43 (Energy & Macro) | Decent on tariffs/energy; thin on geopolitical events | Add: `pandemic`, `COVID-19`, `lockdown` (currently in `excluded_signals` adjacent — debate: should pandemic be in scope?), `Brexit`, `referendum`, `Article 50`, `Ukraine invasion` (named narrative events) |
| `policy_fiscal` | E62, H6 (Budget, Deficit, Debt) | Covers core fiscal vocabulary | Add: `Build Back Better`, `Inflation Reduction Act`, `IRA`, `CHIPS Act` (named legislation — debatable as keywords vs. entities); `government shutdown`, `continuing resolution` |
| `housing_and_consumer` | E21 (Consumption), R31 (Housing Demand) | Good on mortgage/sentiment | Add: `real consumption`, `discretionary spending`, `housing starts`, `building permits`, `purchase application` |

### Excluded JEL areas (intentional)

These should remain excluded — they pollute macro narrative detection without
adding signal:

- **D** Microeconomics — game theory, contract theory, choice theory
- **I** Health, Education, Welfare — public health programs (separate from
  pandemic macro effects), education policy
- **J** Labor Economics (general) — labor market structure beyond aggregate
  employment is E2-scope, not macro narrative
- **L** Industrial Organization
- **M** Business Administration / Marketing
- **N** Economic History (except via macro_themes when relevant)
- **O** Economic Development — country-level dev econ unless macro-financial
- **Q** Agriculture (except energy → already E3-relevant)
- **R** Urban/Regional (except housing → already E21-relevant)
- **Z** Cultural / Sports / Other Special Topics

### Notable anchor narratives and their JEL fit

The 10 anchor narratives map cleanly to in-scope JEL codes:

| Anchor | Primary JEL | Notes |
|---|---|---|
| SVB collapse | G21, G28 | Banking stress + regulation |
| COVID market crash | E32, F62, G14 | Macro shock + global imbalances + market dynamics |
| Brexit aftermath | F4, F31, F51 | Trade-finance-geopolitics complex |
| Transitory inflation debate | E31, E52 | Inflation + monetary policy |
| Credit Suisse stress | G21, G2 | Banking institution failure |
| Regional banking contagion | G21, G28 | Banking + regulation |
| 2022 inflation peak | E31, E52 | Inflation + monetary policy |
| Soft landing emergence | E32, E52 | Business cycle narrative |
| 2013 taper tantrum | E52, G12 | Monetary policy → asset price reaction |
| 2015 China devaluation | F31, F4 | FX + international finance |

All ten anchors require keywords from **at least two of** {E, F, G} top-level
codes, confirming the macro-financial scope is the right operating domain.

---

## Recommendation

### 1. Restructure `topic_filter_keywords.yaml` with JEL provenance

Add a `jel_codes` block at the top declaring the in-scope codes, and annotate
each category with the JEL subcode(s) it operationalizes. The category names
stay as practical groupings; JEL annotation is the citable artifact.

Sketch of the proposed header:

```yaml
schema_version: "2.0.0"
methodology:
  taxonomy: "JEL Classification System (American Economic Association)"
  in_scope_codes:
    - E   # Macroeconomics and Monetary Economics (all subcodes)
    - F   # International Economics (subcodes F1, F3, F4, F5, F6)
    - G   # Financial Economics (subcodes G1, G2, G33)
    - H6  # National Budget, Deficit, Debt (fiscal narrative subset)
  out_of_scope_codes:
    - D, I, J (general), L, M, N, O, Q (except Q4), R (except R31), Z
  rationale_doc: docs/filter_audit_jel.md

categories:
  core_macro:
    jel: [E31, E32]
    keywords:
      - inflation
      - ...
```

### 2. Apply the additions from the audit table above

Each addition is justified by a JEL subcode it operationalizes. Total
additions: ~50 keywords across 11 categories. Total list size after additions:
~220 keywords (currently ~170). The keyword_min_matches threshold (currently 2)
can stay — the canonical list is dense enough that 2 matches remain
specific.

### 3. Decide on pandemic, Brexit, named legislation

These are NAMED EVENTS / LEGISLATION rather than macro CONCEPTS. Two options:

- **(A) Include as keywords** — directly captures anchor-relevant content
  (helps COVID/Brexit anchor recovery). Risk: keyword list drifts toward
  entity recognition rather than topic operationalization.
- **(B) Keep keyword list concept-focused; rely on embedding gate to capture
  named events** — preserves taxonomic purity. Risk: under-capture of named
  events if seed articles don't cover them well.

**My recommendation: (A).** Anchor narratives are the validation criterion,
and explicit inclusion is more defensible than relying on the embedding
gate's implicit coverage. List the named events under a new `named_events`
category with a methodology note: "Named macro shocks and policy events
referenced as narrative anchors. Each entry corresponds to a JEL-in-scope
shock and is documented in `data/anchors/anchor_narratives.jsonl`."

### 4. Eliminate inline Stage 1 filters from all broad-source ingestors

This is the most consequential recommendation and the answer to "are we
ingesting based on filters that leave content out": **yes, currently, and we
should stop.**

Three options for what to do:

- **(A) Remove inline filters entirely; canonical Stage 2 filter only.**
  Most defensible methodologically — ingest is content-neutral, all filtering
  happens in one auditable step. Cost: significantly longer ingest time
  (~20 hours for unfiltered Brookings vs. ~30 min currently; CBO is blocked
  anyway).
- **(B) Replace inline filters with the SAME canonical YAML keyword list.**
  Same filter at both stages → no asymmetric loss. Ingest stays bandwidth-
  bounded. Easy to defend ("we filter consistently at ingest and at corpus
  definition, using the same JEL-anchored keyword set").
- **(C) Strict subset constraint:** inline filter is a *broader* superset of
  the canonical filter — admits everything the canonical filter would, plus
  some borderline content that the canonical filter then drops. Still
  ingests less than (A) but no asymmetric loss.

**My recommendation: (B).** Option (A) is the platonic ideal but the
20-hour Brookings ingest is real wall time, and the canonical filter
discards the same content (B) avoids ingesting in the first place. Both
(A) and (B) are equally defensible — neither loses content asymmetrically.
(B) is strictly faster.

### 5. Apply the canonical filter to PIIE

Currently PIIE has no Stage 1 filter (and the small ~179 article count
suggests it doesn't need one). But after the PIIE undercapture bug is fixed
(task #16), the article count will increase substantially. Apply the
canonical filter to PIIE for consistency. Same filter, every source.

---

## Implementation plan

| Step | Work | Output | Effort |
|---|---|---|---|
| 1 | Author ADR-015 (proposed) — methodology decision record | `docs/architecture_decisions.md` | 30 min |
| 2 | Audit + edit YAML — add JEL annotations, missing keywords, new `named_events` category | `config/topic_filter_keywords.yaml` | 1-2 hr |
| 3 | Refactor inline ingestor filters to load canonical YAML | `src/mnd/ingestion/institutional.py` | 1 hr |
| 4 | Re-run filter step on existing corpus (no re-ingest needed) | `data/processed/articles.parquet` | ~15 min |
| 5 | Re-cluster (post-filter changes) | `data/processed/clusters.parquet` | ~10 min on GPU |
| 6 | Re-validate anchor recovery against the refactored corpus | stdout | ~5 min |

The cumulative compute cost is ~40 min on RCC; the cumulative code/audit
work is half a day. Done before pre-registration freeze, this hardening
eliminates a methodology criticism that would otherwise need a long
"limitations" paragraph in the technical report.

---

## Citations and references

- American Economic Association, *Journal of Economic Literature Classification
  System*. https://www.aeaweb.org/jel/guide/jel.php
- Shiller, R. (2017). *Narrative Economics.* American Economic Review 107(4).
  — Framing for narrative-focused macro research.
- This document supersedes the inline keyword lists currently in
  `src/mnd/ingestion/institutional.py:1078, 1700, 1830, 2038, 2471`.
