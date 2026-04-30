# Pre-Registration: Macro Narrative Dynamics

**Document version**: 1.0.0-DRAFT
**Status**: ⚠️  This document is a TEMPLATE. It MUST be finalized and
publicly timestamped (via OSF, or a signed git tag) BEFORE any predictive
analysis touches the held-out 2020–present validation period. See
plan §8.4.

**Locked**: <!-- INSERT DATE WHEN COMMITTED -->
**Public timestamp**: <!-- OSF DOI or signed git tag -->
**Authors**: <!-- INSERT -->

---

## 1. Project & Hypotheses

### 1.1 Background

This project measures narrative dynamics in U.S. financial discourse from 2010
to present, fitting epidemiological growth models to article-level time series
clustered into coherent narratives. See `docs/` for the full project plan.

### 1.2 Confirmatory hypotheses

The following hypotheses are pre-specified and tested against the held-out
period (2020–present). Each is paired with a falsification criterion.

**H1 — Anchor narrative recovery.**
The system recovers ≥ 7 of 10 documented anchor narratives (see
`data/anchors/anchor_narratives.jsonl`) within the per-anchor `tolerance_days`
window.

> *Falsified if* < 7 of 10 anchors recovered. *Response*: per kill criterion 2,
> debug embedding/filtering; if persistent, shift to novelty-velocity framework.

**H2 — Cluster stability under bootstrapping.**
Across 20 bootstrap replicates with deterministic seeds, the median
Normalized Mutual Information (NMI) between clusterings of the medium-granularity
narratives is ≥ 0.40.

> *Falsified if* median bootstrap NMI < 0.40 across all parameter settings
> in the strict/default/permissive sweep. *Response*: per kill criterion 1,
> narrow to inflation-only fallback scope.

**H3 — Dynamics-model goodness-of-fit.**
Across the validation set, median $R^2$ for the best-of-four-models fit is
≥ 0.30, AND the posterior credible interval on $R_0$ is < 2.0 units wide.

> *Falsified if either threshold breached*. *Response*: per kill criterion 3,
> drop SIR; fall back to logistic growth or non-parametric raw curve features.

### 1.3 Exploratory hypotheses (NOT held-out tests)

The following are exploratory — reported with FDR correction but **not**
held-out tests of the framework's validity.

**H4 — Narrative-volatility association.** Periods of high narrative-emergence
volume in inflation- and recession-related clusters are associated with
elevated VIX and elevated breakeven inflation volatility, controlling for
realized macro surprise. Tested with Granger causality in both directions.

> *Reported direction*: This is a descriptive association test, not a causal
> claim. Both Granger directions are reported.

**H5 — Historical-analog similarity.** Emerging narratives (early-stage clusters
in the held-out period) have measurable similarity to historical predecessors
in (a) keyword vocabulary, (b) embedding-space proximity, (c) fitted growth
parameters.

> *Reported as*: a descriptive characterization, not a predictive claim.

---

## 2. Variables & Operationalization

### 2.1 Independent variables

- **Narrative cluster ID** (medium-granularity BERTopic output, locked parameters)
- **Cluster life-cycle stage** (pre-emergence, early-spread, peak, decay, dormant)
- **Estimated $R_0$** (Bayesian posterior mean, with credible interval)
- **Cluster article volume** (daily count, 7-day centered MA smoothed)

### 2.2 Outcome variables (for exploratory tests)

- **VIX** (`VIXCLS` from FRED)
- **5-year breakeven inflation** (`T5YIE` from FRED)
- **High yield spread** (`BAMLH0A0HYM2`)
- **2y-10y Treasury spread** (`T10Y2Y`)
- **NBER recession indicator** (binary, business-cycle-dating series)
- **Realized monthly CPI surprise** vs. consensus (Bloomberg or Atlanta Fed)

### 2.3 Time horizons tested

For exploratory associations: 5, 10, 20, 60 trading days forward.
All horizons reported; no horizon-cherry-picking.

### 2.4 Statistical tests

- **Anchor recovery (H1)**: pass/fail per anchor, count over 10.
- **Cluster stability (H2)**: bootstrap NMI distribution, median + 95% bootstrap CI.
- **Dynamics fit (H3)**: $R^2$ distribution; $R_0$ posterior CI width distribution.
- **Granger (H4)**: full bidirectional VAR, lag selection by BIC, 4-lag default.
- **Historical analog (H5)**: cosine similarity in embedding space, Mahalanobis
  distance in growth-parameter space; Spearman rank correlation between methods.

### 2.5 Multiple-comparison correction

All exploratory hypothesis tests are reported with **Benjamini-Hochberg FDR**
correction at α = 0.05. Both raw $p$-values and FDR-adjusted $q$-values are
reported.

---

## 3. Data & Window

- **Training window**: 2010-01-01 through 2019-12-31. Used for hyperparameter
  tuning, anchor validation on pre-2020 anchors, and stability analysis.
- **Held-out window**: 2020-01-01 through `auto` (today − 7d, refreshed weekly).
  Examined ONLY in final analysis.
- **Pre-2010 data**: deliberately excluded (see plan §3.3).
- **Outlets**: per `config/whitelist.yaml`, locked at the schema_version
  committed alongside this pre-registration.

---

## 4. Decision Rules

### 4.1 If H1, H2, or H3 is falsified

Per kill criteria, the project pauses for diagnostic work. If the diagnostic
suggests an unrecoverable issue, the project pivots to the inflation-only
fallback scope (plan §9.1) and re-runs the full validation under that scope.
A second pre-registration is committed before the new validation runs.

### 4.2 If exploratory hypotheses fail FDR correction

Reported as a null result. Per kill criterion 4, this is **not** a project
killer. The descriptive contribution stands.

### 4.3 If anchor recovery is partial (e.g., 8 of 10)

Project proceeds. Failed anchors are documented as known limitations of the
methodology — including specifically *why* each failed (was the cluster too
diffuse? Did the topic filter exclude relevant articles? Did the time
discretization miss the emergence?). The dashboard's "what is this" page
documents these limitations.

---

## 5. Out-of-Sample Discipline

- **Data isolation**: held-out articles (2020-present) are not loaded into
  any clustering, embedding, or hyperparameter-tuning step until final analysis.
- **Random seed**: globally pinned (`reproducibility.global_random_seed: 42`).
- **No iterative refinement on held-out**: the parameters and methodology
  locked at pre-registration are the parameters used for held-out evaluation.
  Any change after this document is committed requires either (a) a new
  pre-registration, or (b) explicit labeling of subsequent results as
  "post-hoc exploratory."

---

## 6. Reporting Standards

Following plan §10.4:

- All quantitative claims report 95% bootstrap confidence intervals.
- All multiple-comparison contexts report raw $p$ AND FDR-adjusted $q$.
- Any portfolio-style framing in exploratory analysis reports the Deflated
  Sharpe Ratio (Bailey & López de Prado).
- Visualizations distinguish training-set fits from held-out predictions
  with explicit color/label coding.

---

## 7. Deviations Log

Any deviation from this pre-registration during execution is logged here
with date, rationale, and impact. Deviations do not invalidate the
pre-registration; they make it auditable.

| Date | Deviation | Rationale | Impact on hypothesis tests |
| --- | --- | --- | --- |
| _N/A_ | _none yet_ | | |

---

## 8. Public timestamp

This document is committed to OSF (or signed git tag) at the time it transitions
from DRAFT to LOCKED. The commit/DOI is recorded at the top of this document.
The corresponding `config/config.yaml` schema_version is also recorded.
