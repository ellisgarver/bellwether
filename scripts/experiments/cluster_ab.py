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


# ---------------------------------------------------------------------------
# Tier-0 gold benchmark + shared clustering helpers (research, no pipeline use)
# ---------------------------------------------------------------------------

def _load_gold(path: str = "scripts/experiments/narrative_gold.json") -> list[dict]:
    p = Path(path)
    if not p.exists():
        p = Path(__file__).resolve().parent / "narrative_gold.json"
    return json.loads(p.read_text())["narratives"]


def _score_gold(mf: pd.DataFrame, terms_by_topic: dict[int, list[str]] | None,
                gold: list[dict], topic_col: str = "topic") -> dict:
    """Score one clustering against the hand-labelled narratives (Tier 0).

    For each gold narrative, find the cluster whose c-TF-IDF terms best overlap
    its keyword set, then measure how concentrated that cluster's articles are in
    the narrative's active window. A story-like clustering matches the terms AND
    concentrates in-window; a bucket matches the terms but sprawls across the
    corpus. Persistent narratives (r-star, climate) are excluded from the
    concentration average — a low value there is correct, not a miss.
    """
    m = mf[mf[topic_col] != -1].drop_duplicates(subset=[topic_col, "article_id"])
    dates_by = {int(t): g["published_at"] for t, g in m.groupby(topic_col)}
    term_str = {int(t): " ".join(w.lower() for w in ws)
                for t, ws in (terms_by_topic or {}).items()}
    per: list[dict] = []
    for nar in gold:
        gterms = [t.lower() for t in nar["terms"]]
        best_t, best_ov = None, 0
        for t, s in term_str.items():
            ov = sum(1 for g in gterms if g in s)
            if ov > best_ov:
                best_ov, best_t = ov, t
        rec: dict = {"name": nar["name"], "persistent": bool(nar.get("persistent", False)),
                     "overlap": int(best_ov), "matched_topic": best_t,
                     "found": bool(best_ov >= 2)}
        if rec["found"]:
            d = pd.to_datetime(dates_by[best_t], utc=True, errors="coerce").dropna()
            start = pd.Timestamp(nar["start"], tz="UTC")
            end = pd.Timestamp(nar["end"], tz="UTC") + pd.offsets.MonthEnd(0)
            rec["in_window_frac"] = round(float(((d >= start) & (d <= end)).mean()), 3) if len(d) else 0.0
            rec["matched_span_y"] = round(float((d.max() - d.min()).days / 365.25), 2) if len(d) else 0.0
            rec["matched_size"] = int(len(d))
        per.append(rec)
    found = [r for r in per if r["found"]]
    ep = [r for r in found if not r["persistent"]]
    return {
        "recall": round(len(found) / max(len(gold), 1), 3),
        "concentration_episodic": round(float(np.mean([r["in_window_frac"] for r in ep])), 3) if ep else None,
        "median_matched_span_y": round(float(np.median([r["matched_span_y"] for r in found])), 2) if found else None,
        "per_narrative": per,
    }


def _cluster_terms(docs: list[str], labels, topn: int = 8, max_chars: int = 500) -> dict[int, list[str]]:
    """Lightweight c-TF-IDF terms per label (each cluster = one concatenated doc).

    Mirrors BERTopic's c-TF-IDF closely enough for the diagnostics without
    instantiating a full model. Stays sparse throughout so a many-thousand-cluster
    grid does not densify a clusters x vocab matrix.
    """
    from sklearn.feature_extraction.text import CountVectorizer

    labels = np.asarray(labels)
    uniq = [int(l) for l in sorted(set(labels.tolist())) if l != -1]
    if not uniq:
        return {}
    texts = [" ".join(docs[i][:max_chars] for i in np.nonzero(labels == l)[0]) for l in uniq]
    cv = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, max_features=40000)
    X = cv.fit_transform(texts).astype(float)
    rs = np.asarray(X.sum(axis=1)).ravel()
    rs[rs == 0] = 1.0
    tf = X.multiply((1.0 / rs)[:, None])
    df_ = np.asarray((X > 0).sum(axis=0)).ravel()
    idf = np.log(1.0 + X.shape[0] / (1.0 + df_))
    ctf = tf.multiply(idf.reshape(1, -1)).tocsr()
    vocab = np.array(cv.get_feature_names_out())
    out: dict[int, list[str]] = {}
    for r, l in enumerate(uniq):
        row = ctf.getrow(r)
        if row.nnz == 0:
            out[l] = []
            continue
        order = row.indices[np.argsort(row.data)[::-1][:topn]]
        out[l] = [str(vocab[j]) for j in order]
    return out


def _umap_reduce(embeddings, cfg, n_components: int):
    from umap import UMAP

    u = cfg["clustering"]["umap"]
    return UMAP(n_neighbors=u["n_neighbors"], min_dist=u["min_dist"],
                n_components=n_components, metric=u["metric"],
                random_state=u["random_state"]).fit_transform(embeddings)


def _hdbscan_labels(reduced, min_cluster_size: int, method: str, cfg):
    from hdbscan import HDBSCAN

    h = cfg["clustering"]["hdbscan"]
    return HDBSCAN(min_cluster_size=min_cluster_size, cluster_selection_method=method,
                   metric=h["metric"], prediction_data=False).fit_predict(reduced)


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


def arm_grid(cfg, components: list[int], mcs_list: list[int], methods: list[str]) -> dict:
    """Resolution sweep on the CACHED embeddings — no re-embed (Tier 1).

    For each UMAP ``n_components`` (fit once, the expensive step), sweep HDBSCAN
    ``min_cluster_size`` x ``cluster_selection_method`` (cheap). Reports the four
    bucket-vs-story diagnostics plus the Tier-0 gold recall/concentration for
    every cell, so we can read whether finer resolution breaks the long-lived
    buckets into time-localized stories without paying GPU cost.
    """
    clusters_df, embeddings = _load_base(cfg)
    if not clusters_df.index.equals(pd.RangeIndex(len(clusters_df))):
        clusters_df = clusters_df.reset_index(drop=True)
    docs = _docs_from(clusters_df)
    gold = _load_gold()
    results: list[dict] = []
    for nc in components:
        log.info("grid: UMAP fit n_components=%d on %d docs", nc, len(clusters_df))
        reduced = _umap_reduce(embeddings, cfg, nc)
        for mcs in mcs_list:
            for method in methods:
                labels = _hdbscan_labels(reduced, mcs, method, cfg)
                mf = _member_frame(
                    clusters_df.assign(topic_ab=labels), "topic_ab"
                ).rename(columns={"topic_ab": "topic"})
                terms = _cluster_terms(docs, labels)
                m = cluster_metrics(mf, terms)
                g = _score_gold(mf, terms, gold)
                row = {
                    "n_components": nc, "min_cluster_size": mcs, "selection": method,
                    "n_clusters": m["n_clusters"], "n_ge_42": m["n_ge_42"],
                    "noise_share": m["noise_share"],
                    "duration_median_y": m["duration_median_y"],
                    "share_gt10y": m["share_gt10y"],
                    "single_source_ge90_share": m["single_source_ge90_share"],
                    "person_top5_share": m["person_top5_share"],
                    "gold_recall": g["recall"],
                    "gold_concentration": g["concentration_episodic"],
                    "gold_median_span_y": g["median_matched_span_y"],
                }
                results.append(row)
                log.info("  mcs=%d %-4s → clusters=%d ge42=%d gt10y=%.2f gold_conc=%s span=%s",
                         mcs, method, m["n_clusters"], m["n_ge_42"],
                         m["share_gt10y"], g["concentration_episodic"],
                         g["median_matched_span_y"])
    return {"grid": results, "baseline_control": arm_control(cfg)}


def arm_probe(cfg, top_k: int, sub_mcs: int) -> dict:
    """Sub-cluster the largest surfaced buckets on their own members (Tier 1).

    The single most diagnostic test: for each of the ``top_k`` biggest >=42
    clusters, re-reduce and re-cluster ONLY that bucket's member embeddings at
    fine resolution (leaf, small min_cluster_size). If coherent (framing x era)
    sub-clusters fall out with much shorter spans than the parent, the framings
    are separable in the current embedding space and the fix is a cheap
    resolution change. If they do not, the embedding geometry blends framings and
    a re-embed is required. Reads whether we are on the cheap or expensive branch.
    """
    clusters_df, embeddings = _load_base(cfg)
    if not clusters_df.index.equals(pd.RangeIndex(len(clusters_df))):
        clusters_df = clusters_df.reset_index(drop=True)
    df = _member_frame(clusters_df)
    docs = _docs_from(clusters_df)
    parent_terms = _terms_from_topic_info("data/processed/topic_info.parquet")
    nc = int(cfg["clustering"]["umap"]["n_components"])

    sizes = df[df["topic"] != -1].groupby("topic")["article_id"].nunique().sort_values(ascending=False)
    targets = [int(t) for t in sizes[sizes >= 42].index[:top_k]]
    out: list[dict] = []
    for tid in targets:
        rows = df[df["topic"] == tid]
        idx = rows.index.to_numpy()
        emb = embeddings[idx]
        pdt = pd.to_datetime(rows.drop_duplicates("article_id")["published_at"], utc=True).dropna()
        pspan = float((pdt.max() - pdt.min()).days / 365.25) if len(pdt) else 0.0
        reduced = _umap_reduce(emb, cfg, nc) if len(emb) > (nc + 2) * 5 else emb
        sub = _hdbscan_labels(reduced, sub_mcs, "leaf", cfg)
        sub_terms = _cluster_terms([docs[i] for i in idx], sub)
        subframe = rows.assign(_sub=sub)
        subs: list[dict] = []
        for sid, g in subframe[subframe["_sub"] != -1].groupby("_sub"):
            gd = pd.to_datetime(g.drop_duplicates("article_id")["published_at"], utc=True).dropna()
            subs.append({
                "sub": int(sid), "n_articles": int(g["article_id"].nunique()),
                "span_y": round(float((gd.max() - gd.min()).days / 365.25), 2) if len(gd) else 0.0,
                "center": str(gd.mean().date()) if len(gd) else None,
                "terms": sub_terms.get(int(sid), [])[:8],
            })
        subs.sort(key=lambda s: -s["n_articles"])
        med_sub = float(np.median([s["span_y"] for s in subs])) if subs else None
        centers = sorted(s["center"] for s in subs if s["center"])
        out.append({
            "parent_topic": tid, "parent_terms": parent_terms.get(tid, [])[:8],
            "parent_n_articles": int(sizes[tid]), "parent_span_y": round(pspan, 2),
            "n_subclusters": len(subs),
            "sub_noise_share": round(float((np.asarray(sub) == -1).mean()), 3),
            "median_sub_span_y": round(med_sub, 2) if med_sub is not None else None,
            "sub_center_range": [centers[0], centers[-1]] if centers else None,
            "subclusters": subs[:12],
        })
        log.info("probe topic %d (n=%d span=%.1fy) → %d subs, median sub span %s",
                 tid, int(sizes[tid]), pspan, len(subs), med_sub)
    return {"top_k": top_k, "sub_min_cluster_size": sub_mcs, "buckets": out}


def arm_hier(cfg, parent_floor: int, sub_mcs: int, sub_method: str) -> dict:
    """Two-level (divisive) clustering: keep the flat topic as the THEME, then
    sub-cluster each theme on its own member embeddings to expose the STORIES.

    The probe generalized to every theme and SCORED on the gold set at the leaf
    level. This is the direct test of whether (theme x episode) is the right
    unit of analysis: a flat pass gives 14-year persistent buckets, but the probe
    showed the mini-stories separate cleanly inside each bucket. Here the leaves
    become the narratives and we measure gold recall / in-window concentration /
    span on them, comparably to the flat baseline and the grid cells.

    Divisive (split down), not BERTopic's agglomerative ``hierarchical_topics``
    (merge up): the problem is persistent buckets that must be SPLIT, and drift
    already showed they would not merge with their own past. Runs on the CACHED
    embeddings — no re-embed. A theme that does not sub-divide (HDBSCAN returns
    all-noise) is kept whole as a single leaf, so a coherent short narrative is
    never lost to leaf noise.
    """
    clusters_df, embeddings = _load_base(cfg)
    if not clusters_df.index.equals(pd.RangeIndex(len(clusters_df))):
        clusters_df = clusters_df.reset_index(drop=True)
    docs = _docs_from(clusters_df)
    gold = _load_gold()
    topic = clusters_df["topic"].to_numpy()
    nc = int(cfg["clustering"]["umap"]["n_components"])

    sizes = pd.Series(topic[topic != -1]).value_counts()
    targets = [int(t) for t in sizes[sizes >= parent_floor].index]
    leaf = np.full(len(clusters_df), -1, dtype=int)
    next_id = 0
    leaf_spans: list[float] = []
    dts = pd.to_datetime(clusters_df["published_at"], utc=True, errors="coerce")
    for tid in targets:
        idx = np.nonzero(topic == tid)[0]
        emb = embeddings[idx]
        reduced = _umap_reduce(emb, cfg, nc) if len(emb) > (nc + 2) * 5 else emb
        sub = _hdbscan_labels(reduced, sub_mcs, sub_method, cfg)
        groups = [np.nonzero(sub == s)[0] for s in sorted(set(sub)) if s != -1]
        if not groups:                      # theme did not divide — keep it whole
            groups = [np.arange(len(idx))]
        for g in groups:
            sel = idx[g]
            leaf[sel] = next_id
            gd = dts.iloc[sel].dropna()
            if len(gd):
                leaf_spans.append(float((gd.max() - gd.min()).days / 365.25))
            next_id += 1

    mf = _member_frame(clusters_df.assign(topic_ab=leaf), "topic_ab").rename(
        columns={"topic_ab": "topic"})
    terms = _cluster_terms(docs, leaf)
    hier_metrics = cluster_metrics(mf, terms)
    hier_gold = _score_gold(mf, terms, gold)

    # Flat baseline on the same corpus, for a like-for-like comparison.
    flat_terms = _terms_from_topic_info("data/processed/topic_info.parquet")
    flat_mf = _member_frame(clusters_df)
    flat_metrics = cluster_metrics(flat_mf, flat_terms)
    flat_gold = _score_gold(flat_mf, flat_terms, gold)

    ls = pd.Series(leaf_spans)
    return {
        "parent_floor": parent_floor, "sub_min_cluster_size": sub_mcs,
        "sub_method": sub_method, "n_themes_split": len(targets),
        "n_leaves": int(next_id),
        "leaf_span_median_y": float(ls.median()) if len(ls) else None,
        "leaf_span_p90_y": float(ls.quantile(0.9)) if len(ls) else None,
        "leaf_share_gt10y": float((ls > 10).mean()) if len(ls) else None,
        "hier": {
            "n_ge_42": hier_metrics["n_ge_42"],
            "duration_median_y": hier_metrics["duration_median_y"],
            "share_gt10y": hier_metrics["share_gt10y"],
            "single_source_ge90_share": hier_metrics["single_source_ge90_share"],
            "gold_recall": hier_gold["recall"],
            "gold_concentration": hier_gold["concentration_episodic"],
            "gold_median_span_y": hier_gold["median_matched_span_y"],
        },
        "flat_baseline": {
            "n_ge_42": flat_metrics["n_ge_42"],
            "duration_median_y": flat_metrics["duration_median_y"],
            "share_gt10y": flat_metrics["share_gt10y"],
            "single_source_ge90_share": flat_metrics["single_source_ge90_share"],
            "gold_recall": flat_gold["recall"],
            "gold_concentration": flat_gold["concentration_episodic"],
            "gold_median_span_y": flat_gold["median_matched_span_y"],
        },
        "gold_per_narrative": hier_gold["per_narrative"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True,
                    choices=["control", "leaf", "sliced", "drift", "grid", "probe", "hier"])
    # grid (Tier 1 resolution sweep) knobs
    ap.add_argument("--grid-components", default="5,15",
                    help="comma-separated UMAP n_components to sweep (grid arm)")
    ap.add_argument("--grid-mcs", default="5,10",
                    help="comma-separated HDBSCAN min_cluster_size to sweep (grid arm)")
    ap.add_argument("--grid-methods", default="eom,leaf",
                    help="comma-separated HDBSCAN selection methods (grid arm)")
    # probe (Tier 1 within-bucket sub-clustering) knobs
    ap.add_argument("--top-k", type=int, default=10,
                    help="number of largest surfaced buckets to probe (probe arm)")
    ap.add_argument("--sub-min-cluster", type=int, default=5,
                    help="HDBSCAN min_cluster_size for sub-clustering (probe/hier arms)")
    # hier (Tier 1 two-level divisive clustering) knobs
    ap.add_argument("--parent-floor", type=int, default=42,
                    help="min theme size to sub-divide (hier arm)")
    ap.add_argument("--sub-method", default="leaf",
                    help="HDBSCAN selection method for sub-clustering (hier arm)")
    args = ap.parse_args()
    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.arm == "grid":
        result = arm_grid(
            cfg,
            [int(x) for x in args.grid_components.split(",") if x],
            [int(x) for x in args.grid_mcs.split(",") if x],
            [m for m in args.grid_methods.split(",") if m],
        )
    elif args.arm == "probe":
        result = arm_probe(cfg, args.top_k, args.sub_min_cluster)
    elif args.arm == "hier":
        result = arm_hier(cfg, args.parent_floor, args.sub_min_cluster, args.sub_method)
    else:
        result = {"control": arm_control, "leaf": arm_leaf,
                  "sliced": arm_sliced, "drift": arm_drift}[args.arm](cfg)
    out = OUT_DIR / f"{args.arm}.json"
    out.write_text(json.dumps(result, indent=2, default=float))
    log.info("arm %s → %s", args.arm, out)
    print(json.dumps(result, indent=2, default=float)[:2000])


if __name__ == "__main__":
    main()
