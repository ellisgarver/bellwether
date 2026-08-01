"""Debate inventory — how many genuine debates does the corpus actually support?

The make-or-break test for the debate-tool reframe: is there a *tool's worth*
(~20+) of contested questions in the corpus, or only a handful (a case study)?

For each sizable cluster we split its documents into two modes (2-component GMM
on the cluster's own doc embeddings) and score whether that split is a genuine
DEBATE or an artifact, using three discriminators:

  - bimodality (dBIC 1-vs-2 on the mode axis): is there really a two-camp split?
  - source segregation (total-variation distance between the two modes' source
    mixes): HIGH = register artifact (BIS-mode vs NBER-mode); LOW = the same
    institutions appear on both sides = the signature of real disagreement.
  - balance (smaller camp's share): a real debate has two substantial camps.

A cluster is a CANDIDATE DEBATE when it is bimodal AND source-mixed AND balanced.
Each mode's distinguishing terms are printed so a human can further separate a
stance debate (transitory-terms vs entrenched-terms) from a mere sub-topic split.

Runs on existing embeddings + clusters (no model, no re-embed).

Usage (RCC, caslake):
  python scripts/experiments/debate_inventory.py --min-docs 100
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

log = get_logger("debate_inventory")
OUT = Path("data/experiments/debate_inventory")


def _mode_terms(texts_a: list[str], texts_b: list[str], topn: int = 7) -> tuple[list[str], list[str]]:
    from sklearn.feature_extraction.text import CountVectorizer
    cv = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_features=4000)
    try:
        X = cv.fit_transform([" ".join(texts_a)[:200000], " ".join(texts_b)[:200000]]).astype(float)
    except ValueError:
        return [], []
    vocab = np.array(cv.get_feature_names_out())
    # c-TF-IDF-ish: term freq per mode, log-odds toward each mode
    tf = X.toarray() + 1.0
    tf = tf / tf.sum(axis=1, keepdims=True)
    lo = np.log(tf[0] / tf[1])
    a = [str(vocab[i]) for i in np.argsort(lo)[::-1][:topn]]
    b = [str(vocab[i]) for i in np.argsort(lo)[:topn]]
    return a, b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-docs", type=int, default=100, help="min distinct articles per cluster to scan")
    ap.add_argument("--bimod-dbic", type=float, default=0.0, help="min dBIC(1-2) to count as bimodal")
    ap.add_argument("--max-segregation", type=float, default=0.5, help="max source TV distance (lower=more mixed)")
    ap.add_argument("--min-balance", type=float, default=0.2, help="min smaller-camp share")
    args = ap.parse_args()
    cfg = load_config()
    OUT.mkdir(parents=True, exist_ok=True)

    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture

    clusters = pd.read_parquet(cfg["paths"]["processed_clusters"]).reset_index(drop=True)
    emb = np.load(cfg["paths"]["processed_embeddings"])
    if emb.shape[0] != len(clusters):
        raise RuntimeError("embeddings/clusters mismatch")
    clusters["text"] = (clusters.get("title").fillna("") + " " + clusters.get("body").fillna("")).str.slice(0, 600)

    rows = []
    sizes = clusters[clusters["topic"] != -1].groupby("topic")["article_id"].nunique()
    targets = [int(t) for t in sizes[sizes >= args.min_docs].index]
    log.info("scanning %d clusters with >=%d docs", len(targets), args.min_docs)

    for tid in targets:
        g = clusters[clusters["topic"] == tid]
        # doc-level: mean-pool chunks per article
        docv, srcs, txts = [], [], []
        for aid, ga in g.groupby("article_id"):
            docv.append(emb[ga.index.to_numpy()].mean(axis=0))
            srcs.append(str(ga.iloc[0].get("source_id")))
            txts.append(str(ga.iloc[0]["text"]))
        V = np.asarray(docv, dtype=np.float32)
        n = len(V)
        if n < args.min_docs:
            continue
        Vn = V / np.clip(np.linalg.norm(V, axis=1, keepdims=True), 1e-9, None)
        k = int(min(30, n - 1, Vn.shape[1]))
        Z = PCA(n_components=k, random_state=42).fit_transform(Vn)
        gm = GaussianMixture(2, covariance_type="full", random_state=42, n_init=4).fit(Z)
        lab = gm.predict(Z)
        if lab.sum() in (0, n):
            lab = (Z[:, 0] > np.median(Z[:, 0])).astype(int)
        axis = Vn[lab == 1].mean(0) - Vn[lab == 0].mean(0)
        proj = (Vn @ axis).reshape(-1, 1)
        b1 = GaussianMixture(1, random_state=42).fit(proj).bic(proj)
        b2 = GaussianMixture(2, random_state=42, n_init=4).fit(proj).bic(proj)
        dbic = float(b1 - b2)

        srcs = np.asarray(srcs)
        nA, nB = int((lab == 0).sum()), int((lab == 1).sum())
        balance = min(nA, nB) / n
        allsrc = sorted(set(srcs))
        cA = Counter(srcs[lab == 0]); cB = Counter(srcs[lab == 1])
        pA = np.array([cA[s] / max(nA, 1) for s in allsrc])
        pB = np.array([cB[s] / max(nB, 1) for s in allsrc])
        tv = float(0.5 * np.abs(pA - pB).sum())     # source segregation

        ta, tb = _mode_terms([t for t, l in zip(txts, lab) if l == 0],
                             [t for t, l in zip(txts, lab) if l == 1])
        is_candidate = (dbic >= args.bimod_dbic and tv <= args.max_segregation
                        and balance >= args.min_balance)
        rows.append({"topic": tid, "n": n, "dbic": round(dbic, 1), "source_tv": round(tv, 2),
                     "balance": round(balance, 2), "candidate": bool(is_candidate),
                     "mode_a_terms": ta, "mode_b_terms": tb})

    rows.sort(key=lambda r: (r["candidate"], -r["dbic"]), reverse=True)
    n_cand = sum(r["candidate"] for r in rows)
    (OUT / "inventory.json").write_text(json.dumps({"n_scanned": len(rows), "n_candidate": n_cand,
                                                    "rows": rows}, indent=2))
    print(f"\nScanned {len(rows)} clusters (>= {args.min_docs} docs).")
    print(f"CANDIDATE DEBATES (bimodal + source-mixed + balanced): {n_cand}")
    print(f"\n{'topic':>6}{'n':>6}{'dBIC':>8}{'srcTV':>7}{'bal':>6}  modeA_terms | modeB_terms")
    for r in rows:
        if not r["candidate"]:
            continue
        print(f"{r['topic']:>6}{r['n']:>6}{r['dbic']:>8}{r['source_tv']:>7}{r['balance']:>6}  "
              f"{', '.join(r['mode_a_terms'][:5])}  |  {', '.join(r['mode_b_terms'][:5])}")


if __name__ == "__main__":
    main()
