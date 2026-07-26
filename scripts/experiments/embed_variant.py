"""Family-E prototype: does a NARRATIVE-STRUCTURED representation cluster better?

Re-embeds a focused, furniture-clean subset of the corpus under alternative
embedding *representations* — a claim/event/time-focused instruction and smaller
chunks — and compares story separation against the current representation on the
SAME documents. Isolates the effect of the representation from the clustering
algorithm and from furniture (it reads the post-filter, disclaimer-stripped
``articles.parquet``), so any gain is attributable to the embedding itself.

Motivation: the dump showed recurring-event narratives (yield curve, debt
ceiling, stablecoins) smear across all their episodes because the current
"policy document" instruction embeds TOPIC, not the specific claim/event. A
claim-focused instruction ("represent the specific economic event, claim, and
time period") plus finer chunks should pull distinct framings apart at the
vector level — the narrative-structured-embedding idea (Mapping News Narratives,
ACM Web Science 2025).

Subset = every article whose text matches >= 1 gold narrative's terms, so the
12 known narratives are all represented while the pass stays a few thousand docs
(minutes of GPU), not the full corpus. Each variant is clustered (UMAP+HDBSCAN,
config defaults) and scored on the gold set with the same harness as cluster_ab.

Usage (RCC GPU, after the rebuild's filter has written a clean articles.parquet):
  python scripts/experiments/embed_variant.py                    # baseline + claim256
  python scripts/experiments/embed_variant.py --variants claim256
  python scripts/experiments/embed_variant.py --sample 8000      # cap the subset
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # cluster_ab helpers

import cluster_ab as cab  # noqa: E402
from mnd.embedding.embedder import Embedder  # noqa: E402
from mnd.processing.chunker import chunk_corpus  # noqa: E402
from mnd.utils.config import load_config  # noqa: E402
from mnd.utils.logging import get_logger  # noqa: E402

log = get_logger("embed_variant")
OUT_DIR = Path("data/experiments/embed_variant")

# Representation variants. "baseline" reproduces the shipped instruction + chunk
# size on this subset (the control); the rest change only the representation.
VARIANTS: dict[str, dict] = {
    "baseline": {
        "instr": "Instruct: Represent this financial policy document for narrative clustering\nQuery: ",
        "tokens": 512, "overlap": 64,
    },
    "claim256": {
        "instr": "Instruct: Represent the specific economic event, claim, and time period described in this text for narrative clustering\nQuery: ",
        "tokens": 256, "overlap": 32,
    },
    "claim512": {
        "instr": "Instruct: Represent the specific economic event, claim, and time period described in this text for narrative clustering\nQuery: ",
        "tokens": 512, "overlap": 64,
    },
}


def _gold_subset(df: pd.DataFrame, gold: list[dict], sample: int | None) -> pd.DataFrame:
    text = (df.get("title").fillna("") + " " + df.get("body").fillna("")).str.lower()
    terms = sorted({t.lower() for nar in gold for t in nar["terms"]}, key=len, reverse=True)
    pat = re.compile("|".join(re.escape(t) for t in terms))
    sub = df[text.str.contains(pat, regex=True, na=False)].reset_index(drop=True)
    if sample and len(sub) > sample:
        sub = sub.sample(sample, random_state=42).reset_index(drop=True)
    return sub


def _run_variant(sub: pd.DataFrame, spec: dict, cfg) -> dict:
    chunks = chunk_corpus(sub, chunk_tokens=spec["tokens"], chunk_overlap=spec["overlap"])
    emb_cfg = cfg["embedding"]["primary"]
    embedder = Embedder(
        model_name=emb_cfg["model"], revision=emb_cfg.get("revision", "main"),
        instruction_aware=True, instruction_prefix=spec["instr"],
        max_seq_len=emb_cfg.get("max_seq_len", 1024),
        batch_size=cfg.get("compute", {}).get("embedding_batch_size", 8),
    )
    vecs = embedder.encode(chunks["body"].tolist(), show_progress=True)

    # Cluster the chunk embeddings exactly as the other arms do, then score gold.
    frame = chunks.rename(columns={"chunk_id": "chunk_id"}).copy()
    frame["topic"] = -1
    reduced = cab._umap_reduce(vecs, cfg, int(cfg["clustering"]["umap"]["n_components"]))
    labels = cab._hdbscan_labels(
        reduced, cfg["clustering"]["hdbscan"]["min_cluster_size"],
        cfg["clustering"]["hdbscan"]["cluster_selection_method"], cfg)
    frame["topic"] = labels
    docs = [f"{t}. {b}" if (t and b) else (t or b or "")
            for t, b in zip(frame.get("title", [""] * len(frame)), frame["body"])]
    terms = cab._cluster_terms(docs, np.asarray(labels))
    mf = cab._member_frame(frame)
    m = cab.cluster_metrics(mf, terms)
    g = cab._score_gold(mf, terms, cab._load_gold())
    return {
        "n_docs": int(len(sub)), "n_chunks": int(len(chunks)),
        "chunk_tokens": spec["tokens"], "instruction": spec["instr"],
        "n_clusters": m["n_clusters"], "noise_share": m["noise_share"],
        "duration_median_y": m["duration_median_y"], "share_gt10y": m["share_gt10y"],
        "single_source_ge90_share": m["single_source_ge90_share"],
        "gold_recall": g["recall"], "gold_concentration": g["concentration_episodic"],
        "gold_median_span_y": g["median_matched_span_y"],
        "gold_per_narrative": g["per_narrative"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="baseline,claim256",
                    help="comma-separated variant names: " + ",".join(VARIANTS))
    ap.add_argument("--sample", type=int, default=None,
                    help="cap the gold-term subset to this many docs (random_state=42)")
    args = ap.parse_args()

    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(cfg["paths"]["processed_articles"])
    gold = cab._load_gold()
    sub = _gold_subset(df, gold, args.sample)
    log.info("Gold-term subset: %d of %d articles", len(sub), len(df))

    results = {}
    for name in [v for v in args.variants.split(",") if v]:
        if name not in VARIANTS:
            log.error("unknown variant %r (have %s)", name, list(VARIANTS)); continue
        log.info("=== variant %s ===", name)
        results[name] = _run_variant(sub, VARIANTS[name], cfg)
        log.info("%s → clusters=%d gold_conc=%s gold_span=%s gt10y=%.2f",
                 name, results[name]["n_clusters"], results[name]["gold_concentration"],
                 results[name]["gold_median_span_y"], results[name]["share_gt10y"])

    out = OUT_DIR / "results.json"
    out.write_text(json.dumps(results, indent=2, default=float))
    log.info("wrote %s", out)
    print("\n%-12s %7s %8s %8s %8s" % ("variant", "clust", "gConc", "gSpan", "gt10y"))
    for name, r in results.items():
        print("%-12s %7d %8s %8s %8.2f" % (
            name, r["n_clusters"], r["gold_concentration"],
            r["gold_median_span_y"], r["share_gt10y"]))


if __name__ == "__main__":
    main()
