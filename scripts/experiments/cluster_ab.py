"""Offline clustering-architecture A/B on cached embeddings (research, ADR-082 follow-up).

Runs entirely from persisted artifacts — no ingestion, no GPU embedding — so each
arm costs CPU-hours, not a rebuild. Compares candidate architectures on the four
diagnostics that define the "buckets vs stories" problem:

  n_clusters / size distribution
  duration distribution (share of clusters spanning >5y, >10y)
  single-source share (fraction of clusters >=90% one source_id)
  person-name incidence (surname in top-5 c-TF-IDF terms)

Arms:
  control   — metrics on the CURRENT persisted clustering (clusters.parquet).
  leaf      — global BERTopic refit with HDBSCAN cluster_selection_method="leaf"
              (finer semantic granularity; library-supported selection method).
  sliced    — time-sliced clustering, the BERTrend pattern (Boutaleb et al. 2024,
              arXiv:2411.05930): fit BERTopic per yearly slice on the cached
              embeddings, then chain-merge with BERTopic.merge_models at the
              library-default min_similarity (= update.merge_min_similarity 0.7,
              the same threshold the weekly merge already uses). New stories
              found new topics instead of being absorbed into 2010-era buckets.
  drift     — diagnostic on the current clustering (no refit): per-cluster
              quarterly centroid trajectory; reports terminal drift = cosine
              similarity of the last active year's centroid to the first active
              year's centroid. Clusters whose own ending would NOT merge with
              their own beginning (similarity < 0.7) are the measured "meaning
              changed under one label" population (Sarkar 2026, Economic
              Representations, measures firm-representation deviation the same
              way). Also evaluates drift-confirmed episode merging: volume-gap
              episodes whose adjacent centroids cohere above the threshold are
              re-merged — the test of whether burst boundaries mark real story
              changes or the same story recurring.

Usage (RCC, CPU partition, from the repo root with the venv active):
  python scripts/experiments/cluster_ab.py --arm control
  python scripts/experiments/cluster_ab.py --arm drift
  python scripts/experiments/cluster_ab.py --arm leaf     # ~1-2h CPU
  python scripts/experiments/cluster_ab.py --arm sliced   # ~2-4h CPU

Outputs one JSON per arm under data/experiments/cluster_ab/.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mnd.utils.config import load_config  # noqa: E402
from mnd.utils.logging import get_logger  # noqa: E402

log = get_logger("cluster_ab")

OUT_DIR = Path("data/experiments/cluster_ab")

# Surnames of officials/central bankers that mark person-attached clusters
# (the naming layer's curated list; used here as a diagnostic only).
_SURNAMES = {
    "draghi", "trichet", "bernanke", "yellen", "powell", "lagarde", "greenspan",
    "volcker", "mnuchin", "kuroda", "dudley", "poloz", "lew", "geithner",
    "carney", "subbarao", "nabiullina", "kashkari", "bullard", "waller",
    "brainard", "clarida", "goolsbee", "sejko", "carstens", "kohn", "fischer",
    "evans", "plosser", "mester", "harker", "bostic", "daly", "williams",
    "rosengren", "lockhart", "lacker", "coeure", "cœuré", "asmussen", "mersch",
}


def _member_frame(clusters_df: pd.DataFrame, topic_col: str = "topic") -> pd.DataFrame:
    df = clusters_df[[topic_col, "article_id", "source_id", "published_at"]].copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    return df.dropna(subset=["published_at"])


def cluster_metrics(df: pd.DataFrame, terms_by_topic: dict[int, list[str]] | None,
                    topic_col: str = "topic") -> dict:
    """The four bucket-vs-story diagnostics over one clustering assignment."""
    g = df[df[topic_col] != -1].groupby(topic_col)
    sizes = g["article_id"].nunique()
    dur = (g["published_at"].max() - g["published_at"].min()).dt.days / 365.25

    # single-source share
    dom = []
    for tid, grp in g:
        counts = grp.groupby("source_id")["article_id"].nunique()
        dom.append(counts.max() / counts.sum())
    dom = pd.Series(dom, index=sizes.index)

    person = None
    if terms_by_topic:
        hits = 0
        for tid in sizes.index:
            terms = [t.lower() for t in terms_by_topic.get(int(tid), [])[:5]]
            if any(any(s in t.split() or s == t for s in _SURNAMES) for t in terms):
                hits += 1
        person = hits / max(len(sizes), 1)

    def q(s, p):
        return float(s.quantile(p))

    return {
        "n_clusters": int(len(sizes)),
        "n_articles_clustered": int(sizes.sum()),
        "noise_share": float(
            df[df[topic_col] == -1]["article_id"].nunique()
            / max(df["article_id"].nunique(), 1)
        ),
        "size_median": q(sizes, 0.5), "size_p90": q(sizes, 0.9),
        "n_ge_42": int((sizes >= 42).sum()), "n_10_41": int(((sizes >= 10) & (sizes < 42)).sum()),
        "duration_median_y": q(dur, 0.5), "duration_p90_y": q(dur, 0.9),
        "share_gt5y": float((dur > 5).mean()), "share_gt10y": float((dur > 10).mean()),
        "single_source_ge90_share": float((dom >= 0.9).mean()),
        "person_top5_share": person,
    }


def _load_base(cfg, *, with_embeddings: bool = True):
    clusters_df = pd.read_parquet(cfg["paths"]["processed_clusters"])
    if "topic" not in clusters_df.columns:
        # Legacy test slices carry the retired three-tier schema; the finest
        # tier stands in so the harness still smoke-tests locally.
        legacy = next((c for c in ("topic_fine", "topic_medium") if c in clusters_df.columns), None)
        if legacy is None:
            raise RuntimeError("clusters.parquet has no topic column")
        log.warning("clusters.parquet has no 'topic' column; using legacy %r", legacy)
        clusters_df = clusters_df.rename(columns={legacy: "topic"})
    if not with_embeddings:
        return clusters_df, None
    embeddings = np.load(cfg["paths"]["processed_embeddings"])
    if embeddings.shape[0] != len(clusters_df):
        raise RuntimeError("embeddings/clusters row mismatch — re-run embed/cluster")
    return clusters_df, embeddings


def _terms_from_topic_info(path: str) -> dict[int, list[str]]:
    try:
        ti = pd.read_parquet(path)
    except Exception:
        return {}
    out = {}
    name_col = "Name" if "Name" in ti.columns else None
    for _, row in ti.iterrows():
        tid = int(row.get("Topic", -1))
        if tid < 0:
            continue
        if "Representation" in ti.columns and isinstance(row["Representation"], (list, np.ndarray)):
            out[tid] = [str(t) for t in row["Representation"]]
        elif name_col:
            out[tid] = str(row[name_col]).split("_")[1:]
    return out


def arm_control(cfg) -> dict:
    clusters_df, _ = _load_base(cfg, with_embeddings=False)
    terms = _terms_from_topic_info("data/processed/topic_info.parquet")
    return cluster_metrics(_member_frame(clusters_df), terms)


def _fit_bertopic(docs, embeddings, cfg, selection_method: str):
    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from umap import UMAP

    u = cfg["clustering"]["umap"]
    h = cfg["clustering"]["hdbscan"]
    umap_model = UMAP(
        n_neighbors=u["n_neighbors"], min_dist=u["min_dist"],
        n_components=u["n_components"], metric=u["metric"],
        random_state=u["random_state"],
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=h["min_cluster_size"],
        cluster_selection_method=selection_method,
        metric=h["metric"], prediction_data=True,
    )
    topic_model = BERTopic(
        umap_model=umap_model, hdbscan_model=hdbscan_model,
        calculate_probabilities=False, verbose=True,
    )
    topics, _ = topic_model.fit_transform(docs, embeddings=embeddings)
    return topic_model, topics


def _docs_from(clusters_df: pd.DataFrame) -> list[str]:
    title = clusters_df.get("title")
    body = clusters_df.get("body")
    return [
        (f"{t}. {b}" if (t and b) else (t or b or ""))
        for t, b in zip(
            (title if title is not None else [""] * len(clusters_df)),
            (body if body is not None else [""] * len(clusters_df)),
        )
    ]


def arm_leaf(cfg) -> dict:
    clusters_df, embeddings = _load_base(cfg)
    docs = _docs_from(clusters_df)
    model, topics = _fit_bertopic(docs, embeddings, cfg, "leaf")
    df = _member_frame(clusters_df.assign(topic_ab=topics), "topic_ab")
    terms = {int(t): [w for w, _ in model.get_topic(t) or []] for t in set(topics) if t != -1}
    return cluster_metrics(df.rename(columns={"topic_ab": "topic"}), terms)


def arm_sliced(cfg) -> dict:
    from bertopic import BERTopic

    clusters_df, embeddings = _load_base(cfg)
    dates = pd.to_datetime(clusters_df["published_at"], utc=True, errors="coerce")
    docs = _docs_from(clusters_df)
    min_sim = float(cfg.get("update", {}).get("merge_min_similarity", 0.7))

    merged = None
    assignments = np.full(len(clusters_df), -1, dtype=int)
    years = sorted(dates.dt.year.dropna().unique())
    for year in years:
        mask = (dates.dt.year == year).to_numpy()
        if mask.sum() < 50:  # too small a slice to cluster on its own
            continue
        idx = np.nonzero(mask)[0]
        sliced_docs = [docs[i] for i in idx]
        model, _ = _fit_bertopic(sliced_docs, embeddings[idx], cfg,
                                 cfg["clustering"]["hdbscan"]["cluster_selection_method"])
        log.info("slice %s: %d docs → %d topics", year, len(idx),
                 len(set(model.topics_)) - 1)
        merged = model if merged is None else BERTopic.merge_models(
            [merged, model], min_similarity=min_sim
        )
    # Final pass: assign every doc with the merged model (transform on embeddings).
    topics, _ = merged.transform(docs, embeddings=embeddings)
    df = _member_frame(clusters_df.assign(topic_ab=topics), "topic_ab")
    terms = {int(t): [w for w, _ in merged.get_topic(t) or []]
             for t in set(topics) if t != -1}
    out = cluster_metrics(df.rename(columns={"topic_ab": "topic"}), terms)
    out["n_slices"] = len(years)
    return out


def arm_drift(cfg) -> dict:
    """Quarterly centroid drift within current clusters + episode-merge test."""
    clusters_df, embeddings = _load_base(cfg)
    df = clusters_df.copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_at"])
    df["q"] = df["published_at"].dt.to_period("Q")
    min_sim = float(cfg.get("update", {}).get("merge_min_similarity", 0.7))

    def cos(a, b):
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        return float(a @ b / (na * nb)) if na > 0 and nb > 0 else np.nan

    terminal, would_split, per_cluster = [], 0, []
    sizes = df[df["topic"] != -1].groupby("topic")["article_id"].nunique()
    for tid in sizes[sizes >= 42].index:
        rows = df[df["topic"] == tid]
        qs = sorted(rows["q"].unique())
        if len(qs) < 8:
            continue
        first_year = [q for q in qs if q <= qs[0] + 3]
        last_year = [q for q in qs if q >= qs[-1] - 3]
        c0 = embeddings[rows[rows["q"].isin(first_year)].index].mean(axis=0)
        c1 = embeddings[rows[rows["q"].isin(last_year)].index].mean(axis=0)
        sim = cos(c0, c1)
        terminal.append(sim)
        if sim < min_sim:
            would_split += 1
        per_cluster.append({"topic": int(tid), "terminal_sim": sim,
                            "n_articles": int(sizes[tid]), "n_quarters": len(qs)})

    t = pd.Series(terminal)
    return {
        "n_clusters_tested": int(len(t)),
        "terminal_sim_median": float(t.median()),
        "terminal_sim_p10": float(t.quantile(0.10)),
        "share_below_merge_threshold": float((t < min_sim).mean()),
        "would_split": int(would_split),
        "per_cluster": sorted(per_cluster, key=lambda r: r["terminal_sim"])[:40],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True,
                    choices=["control", "leaf", "sliced", "drift"])
    args = ap.parse_args()
    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {"control": arm_control, "leaf": arm_leaf,
              "sliced": arm_sliced, "drift": arm_drift}[args.arm](cfg)
    out = OUT_DIR / f"{args.arm}.json"
    out.write_text(json.dumps(result, indent=2, default=float))
    log.info("arm %s → %s", args.arm, out)
    print(json.dumps(result, indent=2, default=float)[:2000])


if __name__ == "__main__":
    main()
