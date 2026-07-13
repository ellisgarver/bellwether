// Build-time artifact loader. Reads the precomputed JSON the Python pipeline
// emits (ADR-043 contract, mnd/dashboard/artifacts.py) from disk at build time and
// embeds it into static pages — the browser never fetches or computes. The data
// dir defaults to the repo's processed-output path; CI can override it.
import fs from "node:fs";
import path from "node:path";

const DATA_DIR =
  process.env.DASHBOARD_DATA_DIR ||
  path.resolve(process.cwd(), "../data/processed/dashboard");

// ---- contract types (mirror artifacts.py; keep in sync via SCHEMA_VERSION) ----

export type Stage = "growth" | "stable" | "decay" | "dormant";

export interface Series {
  dates: string[];
  values: number[];
  freq: string;
}

export interface Fit {
  model: string;
  converged: boolean;
  aicc: number | null;
  peak_time_mean: number | null;
  peak_time_ci: [number, number] | null;
  // Self-standing lens numbers live in `params` (ADR-062): logistic
  // doubling_time/inflection_day/plateau; sir rise_rate/decay_rate/asymmetry/
  // peak_height; bass total_reach/p_innovation/q_imitation. No R0 / Jinf.
  params: Record<string, unknown>;
  curve: number[] | null;
  failure_reason: string | null;
}

export interface Jel {
  code: string;
  in_scope: boolean;
  similarity: number;
  runner_up: string;
  runner_up_gap: number;
}

export interface SimilarPanel {
  semantic: number[];
  lexical: number[];
  morphological: number[];
}

export interface MediaCloud {
  dates: string[];
  story_count: number[];
  ratio: number[];
  reliable_since_year: number;
  caption: string;
  // Press-heating (ADR-064): recent attention-share vs the narrative's yearly
  // baseline. null when there's too little reliable history to judge.
  press_heating?: {
    is_heating: boolean;
    z: number;
    k: number;
    recent_weeks: number;
    baseline_weeks: number;
    caption: string;
  } | null;
}

export interface Markets {
  series_id: string | null;
  series_label: string | null;
  dates: string[];
  volume: number[];
  market: number[];
  granger: Record<string, any>;
  caption: string;
}

export interface RepArticle {
  title: string;
  source_id: string;
  url: string;
  published_at: string;
  excerpt: string;
}

export interface StoryCard {
  cluster_id: number;
  label: string;
  top_terms: string[];
  n_articles: number;
  n_chunks: number;
  date_range: [string, string] | null;
  peak_date: string | null;
  source_mix: [string, number][];
  // Three representative-article panels (ADR-061): core (most central), earliest,
  // newest. Optional so pre-ADR-061 artifacts (only representative_articles) still load.
  central_articles?: RepArticle[];
  earliest_articles?: RepArticle[];
  newest_articles?: RepArticle[];
  representative_articles: RepArticle[];
}

export interface Narrative {
  cluster_id: number;
  label: string;
  // Human-readable display name + one-liner (ADR-056); null → fall back to label.
  label_human: string | null;
  description: string | null;
  stage: Stage;
  card: StoryCard;
  volume: Series;
  fits: Fit[];
  staging_model: string;
  shape_facts: Record<string, number>;
  stage_detail: Record<string, any>;
  jel: Jel | null;
  similar: SimilarPanel | null;
  mediacloud: MediaCloud | null;
  markets: Markets | null;
  schema_version: string;
}

export interface IndexEntry {
  cluster_id: number;
  label: string;
  // Human-readable display name (ADR-056); null → fall back to label.
  label_human?: string | null;
  stage: Stage;
  n_articles: number;
  top_terms: string[];
  peak_date: string | null;
  date_range: [string, string] | null;
  in_scope: boolean;
  jel_code: string | null;
  is_emerging: boolean;
  is_press_heating?: boolean;   // press spiking on this tracked narrative now (ADR-064)
  umap_xy: [number, number] | null;
  umap_xyz: [number, number, number] | null;
  similar_edges: [number, number][];
}

export interface DashboardIndex {
  generated_at: string;
  global_random_seed: number;
  n_narratives: number;
  narratives: IndexEntry[];
  median_article_words: number | null;
  // ADR-051: total non-noise clusters detected vs. the n_narratives surfaced
  // (those with >= min_articles_to_fit articles). Optional — absent in sample data.
  n_clusters_total?: number | null;
  min_articles_to_fit?: number | null;
  // Unique articles in the full clustered corpus (including sub-floor clusters),
  // so the data page can report the whole corpus next to what is surfaced.
  n_articles_corpus?: number | null;
  // Full-corpus composition over every clustered article, not just the surfaced
  // narratives (ADR-076). Absent in older bakes → the data page falls back to
  // aggregating the surfaced story cards.
  corpus_composition?: {
    by_source?: Record<string, number>;
    by_jel?: Record<string, number>;
  } | null;
  schema_version: string;
}

// ---- readers ----

function readJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(path.join(DATA_DIR, file), "utf-8")) as T;
}

export function loadIndex(): DashboardIndex {
  return readJson<DashboardIndex>("index.json");
}

export function loadNarrative(clusterId: number): Narrative {
  return readJson<Narrative>(`narrative_${clusterId}.json`);
}

// ---- optional artifacts (absent in older bakes; pages degrade gracefully) ----

export interface CorpusHeating {
  is_heating: boolean;
  z: number;
  recent_articles: number;
  recent_weeks: number;
  baseline_weeks: number;
  k: number;
}

export interface DirectoryEntry {
  cluster_id: number;
  label: string;
  label_human: string | null;
  n_articles: number;
  date_range: [string, string] | null;
  surfaced: boolean;
  // Forming (ADR-071): sub-floor cluster with a recent onset — listed on the
  // emerging page. Forming entries carry their c-TF-IDF terms for naming.
  forming?: boolean;
  terms?: string[];
  // Corpus heating (ADR-074): baked for sub-floor clusters only (their weekly
  // series never ships); present only where it fires. Surfaced narratives get
  // the same signal computed here in corpusHeating().
  heating?: CorpusHeating;
}

export interface ClusterDirectory {
  generated_at: string;
  n_clusters: number;
  clusters: DirectoryEntry[];
}

export function loadDirectory(): ClusterDirectory | null {
  const p = path.join(DATA_DIR, "clusters_all.json");
  return fs.existsSync(p) ? (JSON.parse(fs.readFileSync(p, "utf-8")) as ClusterDirectory) : null;
}

// ---- corpus heating (ADR-074) ----

// "Heating in the corpus": the narrative's mean weekly article count over the
// most-recent window sits >= kSigma standard errors above its own trailing
// yearly baseline, with at least minArticles in the window. Same shape as the
// baked press-heating signal (recent window vs. own yearly baseline); the z is
// scaled by sqrt(recentWeeks) because institutional volume is single-digit
// weekly counts. Computed here for surfaced narratives from their shipped
// volume series; sub-floor directory clusters carry the equivalent baked blob
// (src/mnd/dashboard/build_artifacts.py — keep parameters in sync with config
// display.corpus_heating).
export const CORPUS_HEATING = {
  recentWeeks: 16,
  baselineWeeks: 52,
  kSigma: 2,
  minArticles: 3,
};

export function corpusHeating(
  volume: Series,
  frontierMs: number,
): { z: number; recent_articles: number } | null {
  const { recentWeeks, baselineWeeks, kSigma, minArticles } = CORPUS_HEATING;
  const WEEK = 7 * 86400e3;
  const times = volume.dates.map((d) => Date.parse(d));
  if (!times.length) return null;
  // Weekly buckets counted back from the corpus frontier; silent weeks are
  // zero (a narrative that went quiet should read as quiet, not be skipped).
  const nWeeks = Math.floor((frontierMs - Math.min(...times)) / WEEK) + 1;
  if (nWeeks < recentWeeks + baselineWeeks) return null;
  const weekly = new Array<number>(nWeeks).fill(0);
  times.forEach((t, i) => {
    const w = Math.floor((frontierMs - t) / WEEK);
    if (w >= 0 && w < nWeeks) weekly[nWeeks - 1 - w] += volume.values[i];
  });
  const recent = weekly.slice(-recentWeeks);
  const base = weekly.slice(-(recentWeeks + baselineWeeks), -recentWeeks);
  const mean = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  const bm = mean(base);
  const sd = Math.sqrt(
    base.reduce((s, v) => s + (v - bm) ** 2, 0) / (base.length - 1),
  );
  if (sd <= 0) return null;
  const z = (mean(recent) - bm) / (sd / Math.sqrt(recentWeeks));
  const recentSum = recent.reduce((s, v) => s + v, 0);
  if (z < kSigma || recentSum < minArticles) return null;
  return { z, recent_articles: recentSum };
}

// ---- press heating (ADR-064 / ADR-074) ----

// "Heating in the press", the symmetric partner of corpus heating: the broad
// press's attention share for a narrative over the recent window sits >= kSigma
// above its own trailing yearly baseline. Same quarterly window as corpus
// heating, so the two panels compare like for like. The z is a raw sigma (no
// sqrt(recentWeeks) scale): press attention share is a dense daily ratio, not
// the sparse integer counts the corpus signal has to correct for. Mirrors the
// baked mnd.detection.mediacloud.press_heating; computed here at build time from
// the shipped ratio series so the window can change without a re-bake (keep in
// sync with config detection.mediacloud.press_heating).
export const PRESS_HEATING = {
  recentWeeks: 16,
  baselineWeeks: 52,
  kSigma: 2,
};

export function pressHeating(
  mc: MediaCloud | undefined,
  frontierMs: number,
): { z: number } | null {
  if (!mc || !mc.dates?.length) return null;
  const { recentWeeks, baselineWeeks, kSigma } = PRESS_HEATING;
  const WEEK = 7 * 86400e3;
  // Weekly means of the attention-share ratio, over reliable years only; silent
  // weeks stay absent (a ratio has no meaningful zero-fill), matching the baked
  // signal's dropna() on the weekly resample.
  const buckets = new Map<number, { sum: number; n: number }>();
  mc.dates.forEach((d, i) => {
    const t = Date.parse(d);
    if (new Date(t).getUTCFullYear() < mc.reliable_since_year) return;
    const w = Math.floor((frontierMs - t) / WEEK);
    if (w < 0) return;
    const b = buckets.get(w) ?? { sum: 0, n: 0 };
    b.sum += mc.ratio[i];
    b.n += 1;
    buckets.set(w, b);
  });
  if (!buckets.size) return null;
  const maxW = Math.max(...buckets.keys());
  const weekly: number[] = [];
  for (let w = maxW; w >= 0; w--) {
    const b = buckets.get(w);
    if (b) weekly.push(b.sum / b.n); // oldest-to-newest, gaps dropped
  }
  if (weekly.length < recentWeeks + baselineWeeks) return null;
  const recent = weekly.slice(-recentWeeks);
  const base = weekly.slice(-(recentWeeks + baselineWeeks), -recentWeeks);
  const mean = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  const bm = mean(base);
  const sd = Math.sqrt(
    base.reduce((s, v) => s + (v - bm) ** 2, 0) / (base.length - 1),
  );
  if (sd <= 0) return null;
  const z = (mean(recent) - bm) / sd;
  if (z < kSigma) return null;
  return { z };
}

// Which surfaced narratives are heating, by signal — one build-time pass so the
// cards, the emerging page, and the narrative pages all badge the same set (the
// baked is_press_heating flag is a 4-week signal; this is the 16-week one the
// emerging page ranks on). Sub-floor clusters are not included (no shipped
// series); their heating is handled from the directory blob on the emerging page.
export function heatingSets(index: DashboardIndex): {
  corpus: Set<number>;
  press: Set<number>;
  frontierMs: number;
} {
  const frontierMs = Math.max(
    ...index.narratives.map((e) => (e.date_range ? Date.parse(e.date_range[1]) : 0)),
  );
  const corpus = new Set<number>();
  const press = new Set<number>();
  for (const e of index.narratives) {
    const n = loadNarrative(e.cluster_id);
    if (corpusHeating(n.volume, frontierMs)) corpus.add(e.cluster_id);
    if (pressHeating(n.mediacloud, frontierMs)) press.add(e.cluster_id);
  }
  return { corpus, press, frontierMs };
}

// Human-readable display name with graceful fallback (ADR-056): the LLM title
// when present, else BERTopic's c-TF-IDF label. One place so card / detail / map
// all render the same name.
export function displayName(e: { label: string; label_human?: string | null }): string {
  return e.label_human || e.label;
}

// Label-by-id lookup so the front end can resolve similar/edge ids → labels
// without hard-coding anything (data-driven per the project constraint).
export function labelMap(index: DashboardIndex): Record<number, string> {
  return Object.fromEntries(
    index.narratives.map((n) => [n.cluster_id, displayName(n)]),
  );
}

// ---- shared display helpers ----

// mirrors the CSS stage palette in styles/global.css (--growth/--stable/
// --decay/--dormant) — keep the two in lockstep.
export const STAGE_COLOR: Record<Stage, string> = {
  growth: "#1f9d6b",
  stable: "#3a5a93",
  decay: "#d1495b",
  dormant: "#9a958a",
};

export const STAGE_LABEL: Record<Stage, string> = {
  growth: "Growth (attention rising)",
  stable: "Stable (sustained plateau)",
  decay: "Decay (attention falling)",
  dormant: "Dormant / unresolved",
};

// JEL macro-finance scope dimensions (ADR-020 basis set: E, F, G, H in-scope).
export const JEL_NAME: Record<string, string> = {
  E: "Macroeconomics & Monetary",
  F: "International Economics",
  G: "Financial Economics",
  H: "Public Economics / Fiscal",
  J: "Labor Economics",
  D: "Microeconomics",
};
