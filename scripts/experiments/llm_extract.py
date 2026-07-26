"""Family-D prototype: does clustering on LLM-EXTRACTED narratives beat text?

The most goal-aligned representation test. Instead of embedding raw prose (which
carries topic, register, and boilerplate), use an LLM to distil each document to
a single structured narrative line — the specific economic CLAIM/EVENT, its
actors, and its time frame — then embed and cluster THOSE. This targets the
"narrative economics" premise directly: two documents about inflation with
different framings ("inflation is transitory" vs "inflation is entrenched")
produce different narrative lines and separate, where raw-text embeddings collapse
them by shared vocabulary (actor-frame-argument extraction, arXiv 2601.10142;
structured event representation, arXiv 2512.19484).

Prototype scope: run on ONE theme (or the gold-term subset) so the LLM pass is a
few hundred–thousand calls, not 121k. Uses the same open model as naming
(gemma3:12b via the Ollama OpenAI-compatible endpoint) so no new infra. Compares
gold story separation of (a) raw-text embedding vs (b) narrative-line embedding
on the same documents.

Usage (RCC, Ollama serving gemma3:12b, GPU for the embedder):
  # start the model once:  ollama serve &   ;  ollama pull gemma3:12b
  python scripts/experiments/llm_extract.py --topic 19          # one theme
  python scripts/experiments/llm_extract.py --gold-subset --sample 1500
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cluster_ab as cab  # noqa: E402
from mnd.embedding.embedder import Embedder  # noqa: E402
from mnd.utils.config import load_config  # noqa: E402
from mnd.utils.logging import get_logger  # noqa: E402

log = get_logger("llm_extract")
OUT_DIR = Path("data/experiments/llm_extract")

_SYSTEM = (
    "You distil an economic text to the single specific narrative it advances. "
    "Reply with one sentence naming the concrete claim or event, the actors, and "
    "the time frame — not the broad topic. Example: 'The Fed signals it will taper "
    "asset purchases in 2013, unsettling bond markets.' No preamble."
)


def _extract_one(base_url: str, model: str, api_key: str | None,
                 title: str, body: str) -> str:
    payload = {
        "model": model, "temperature": 0, "seed": 42,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Title: {title}\n\n{body[:2500]}"},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out["choices"][0]["message"]["content"].strip()


def _cache_path(article_id) -> Path:
    return OUT_DIR / "cache" / f"{article_id}.txt"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", type=int, default=None, help="single theme id to extract")
    ap.add_argument("--gold-subset", action="store_true",
                    help="use the gold-term subset instead of one theme")
    ap.add_argument("--sample", type=int, default=None, help="cap the subset size")
    args = ap.parse_args()

    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cache").mkdir(exist_ok=True)
    nc = cfg.get("display", {}).get("naming", {})
    base_url = os.environ.get("MND_NAMING_BASE_URL", nc.get("base_url", "http://localhost:11434/v1"))
    model = os.environ.get("MND_NAMING_MODEL", nc.get("model", "gemma3:12b"))
    api_key = os.environ.get("MND_NAMING_API_KEY")

    df = pd.read_parquet(cfg["paths"]["processed_articles"])
    if args.gold_subset:
        import re
        gold = cab._load_gold()
        text = (df.get("title").fillna("") + " " + df.get("body").fillna("")).str.lower()
        terms = sorted({t.lower() for n in gold for t in n["terms"]}, key=len, reverse=True)
        pat = re.compile("|".join(re.escape(t) for t in terms))
        sub = df[text.str.contains(pat, regex=True, na=False)].reset_index(drop=True)
    else:
        clusters = pd.read_parquet(cfg["paths"]["processed_clusters"])
        ids = clusters.loc[clusters["topic"] == args.topic, "article_id"].unique()
        sub = df[df["article_id"].isin(ids)].reset_index(drop=True)
    if args.sample and len(sub) > args.sample:
        sub = sub.sample(args.sample, random_state=42).reset_index(drop=True)
    log.info("Extracting narratives for %d articles", len(sub))

    # Extract (cached per article so a rerun is free / resumable).
    lines: list[str] = []
    for i, row in sub.iterrows():
        cp = _cache_path(row["article_id"])
        if cp.exists():
            lines.append(cp.read_text(encoding="utf-8"))
            continue
        try:
            line = _extract_one(base_url, model, api_key,
                                str(row.get("title") or ""), str(row.get("body") or ""))
        except Exception as exc:
            log.warning("extract failed for %s (%s); using title", row["article_id"], exc)
            line = str(row.get("title") or "")
        cp.write_text(line, encoding="utf-8")
        lines.append(line)
        if (i + 1) % 100 == 0:
            log.info("  %d/%d extracted", i + 1, len(sub))
    sub = sub.assign(narrative_line=lines)

    # Embed the narrative lines, cluster, score gold — vs. raw-text baseline.
    emb_cfg = cfg["embedding"]["primary"]
    embedder = Embedder(
        model_name=emb_cfg["model"], revision=emb_cfg.get("revision", "main"),
        instruction_aware=True,
        instruction_prefix="Instruct: Represent this economic narrative for clustering\nQuery: ",
        max_seq_len=emb_cfg.get("max_seq_len", 1024),
        batch_size=cfg.get("compute", {}).get("embedding_batch_size", 8))

    def _cluster_and_score(vecs, texts):
        reduced = cab._umap_reduce(vecs, cfg, int(cfg["clustering"]["umap"]["n_components"]))
        labels = cab._hdbscan_labels(
            reduced, cfg["clustering"]["hdbscan"]["min_cluster_size"],
            cfg["clustering"]["hdbscan"]["cluster_selection_method"], cfg)
        frame = sub.assign(topic=labels)
        terms = cab._cluster_terms(list(texts), np.asarray(labels))
        mf = cab._member_frame(frame)
        m = cab.cluster_metrics(mf, terms)
        g = cab._score_gold(mf, terms, cab._load_gold())
        return {
            "n_clusters": m["n_clusters"], "share_gt10y": m["share_gt10y"],
            "single_source_ge90_share": m["single_source_ge90_share"],
            "gold_recall": g["recall"], "gold_concentration": g["concentration_episodic"],
            "gold_median_span_y": g["median_matched_span_y"],
        }

    narr_vecs = embedder.encode(sub["narrative_line"].tolist(), show_progress=True)
    raw_vecs = embedder.encode(
        (sub.get("title").fillna("") + ". " + sub.get("body").fillna("").str[:2000]).tolist(),
        show_progress=True)
    result = {
        "n_docs": int(len(sub)),
        "narrative_extracted": _cluster_and_score(narr_vecs, sub["narrative_line"]),
        "raw_text": _cluster_and_score(raw_vecs, sub["narrative_line"]),
        "sample_lines": sub["narrative_line"].head(15).tolist(),
    }
    (OUT_DIR / "results.json").write_text(json.dumps(result, indent=2, default=float))
    print("\n%-20s %7s %8s %8s %8s" % ("representation", "clust", "gConc", "gSpan", "gt10y"))
    for k in ("narrative_extracted", "raw_text"):
        r = result[k]
        print("%-20s %7d %8s %8s %8.2f" % (
            k, r["n_clusters"], r["gold_concentration"], r["gold_median_span_y"], r["share_gt10y"]))
    print("\nsample narrative lines:")
    for s in result["sample_lines"][:8]:
        print("  ·", s[:110])


if __name__ == "__main__":
    main()
