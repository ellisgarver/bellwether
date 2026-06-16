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

export type Stage = "growth" | "decay" | "dormant";

export interface Series {
  dates: string[];
  values: number[];
  freq: string;
}

export interface Fit {
  model: string;
  converged: boolean;
  aicc: number | null;
  r0_mean: number | null;
  r0_ci: [number, number] | null;
  peak_time_mean: number | null;
  peak_time_ci: [number, number] | null;
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
  source: string;
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
  representative_articles: RepArticle[];
}

export interface Narrative {
  cluster_id: number;
  label: string;
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
  stage: Stage;
  n_articles: number;
  top_terms: string[];
  peak_date: string | null;
  date_range: [string, string] | null;
  in_scope: boolean;
  jel_code: string | null;
  is_emerging: boolean;
  umap_xy: [number, number] | null;
  umap_xyz: [number, number, number] | null;
  similar_edges: [number, number][];
}

export interface DashboardIndex {
  generated_at: string;
  global_random_seed: number;
  stage_min_r0: number;
  n_narratives: number;
  narratives: IndexEntry[];
  median_article_words: number | null;
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

// Label-by-id lookup so the front end can resolve similar/edge ids → labels
// without hard-coding anything (data-driven per the project constraint).
export function labelMap(index: DashboardIndex): Record<number, string> {
  return Object.fromEntries(index.narratives.map((n) => [n.cluster_id, n.label]));
}

// ---- shared display helpers ----

export const STAGE_COLOR: Record<Stage, string> = {
  growth: "#2e7d32",
  decay: "#c62828",
  dormant: "#78909c",
};

export const STAGE_LABEL: Record<Stage, string> = {
  growth: "Growth (R₀ ≥ 1)",
  decay: "Decay (R₀ < 1)",
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
