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

export const STAGE_COLOR: Record<Stage, string> = {
  growth: "#2e7d32",
  stable: "#1565c0",
  decay: "#c62828",
  dormant: "#78909c",
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
