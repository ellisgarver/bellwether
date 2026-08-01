"""Stance-axis probe — narratives-as-positions, multi-debate stress test.

Models an economic narrative not as a topic cluster but as a POSITION on a
contested question, measured with SemAxis (An, Kwak & Ahn 2018): project each
document's existing embedding onto the axis between two opposing pole framings.
Two validations run per debate:

  1. FACE VALIDITY — held-out example statements for each side (distinct from the
     axis-defining poles) must land on opposite sides with a clear gap. This is
     the stance-vs-intensity discriminator: if the axis only tracked how much a
     topic is discussed, opposing-stance statements would not separate.
  2. REALITY TRACKING — the monthly balance of stance is correlated with the
     relevant FRED series, testing whether the position moves with (and outlives)
     what actually happened.

Calibrated on the CORPUS MEAN (0 = the average document), so the sign is
meaningful without a hand-written "neutral" anchor (which for inflation turned
out to be entrenched-leaning — you cannot write a stance-neutral high-concern
sentence). Runs on EXISTING embeddings (no re-embed); only the ~24 pole/test
sentences are embedded. Fully reversible: reads vectors + FRED, writes one JSON.

Usage (RCC, caslake; fp32 pole embed loads on CPU):
  export FRED_API_KEY=...
  python scripts/experiments/stance_axis.py --debate inflation
  python scripts/experiments/stance_axis.py --debate soft_landing
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

from mnd.embedding.embedder import Embedder  # noqa: E402
from mnd.utils.config import load_config  # noqa: E402
from mnd.utils.logging import get_logger  # noqa: E402

log = get_logger("stance_axis")
OUT_DIR = Path("data/experiments/stance_axis")

# Each debate: which documents engage it, the two pole framings (axis = b - a,
# so stance > 0 leans toward side b), held-out face-validity statements per side,
# and the FRED reality series. Poles and tests are disjoint on purpose.
DEBATES: dict[str, dict] = {
    "inflation": {
        "doc_re": r"\b(inflation|consumer price|cpi|pce|price stability|price pressures|disinflation)\b",
        "label_a": "transitory", "label_b": "entrenched",
        "fred": ("CPIAUCSL", "yoy"),
        "pole_a": [
            "Inflation is transitory and will fade as supply chains normalize.",
            "Price pressures are temporary, driven by pandemic reopening and base effects.",
            "Supply-side bottlenecks are causing a one-off rise in prices that will subside.",
            "Elevated inflation reflects temporary disruptions and should moderate on its own.",
            "Once supply constraints ease, inflation will return to target.",
            "The spike in inflation is driven by transitory factors, not persistent demand.",
        ],
        "pole_b": [
            "Inflation is becoming entrenched and persistent in the economy.",
            "Price pressures are broadening into wages and services, signaling lasting inflation.",
            "Inflation expectations are un-anchoring, making high inflation self-sustaining.",
            "Demand-driven inflation requires sustained monetary tightening to control.",
            "Inflation is proving sticky and will not fade without aggressive rate hikes.",
            "Underlying inflation is durable and broad-based, not a temporary blip.",
        ],
        "test_a": [
            "The recent rise in prices reflects temporary reopening effects and should ease next year.",
            "Bottleneck-driven price increases are a passing phenomenon, not a lasting trend.",
            "The price surge is concentrated in a few reopening-sensitive categories and will fade.",
        ],
        "test_b": [
            "Wage growth and services prices show inflation has become self-reinforcing.",
            "Sticky services inflation means the last mile of disinflation will be slow and hard.",
            "The labor market is too tight to allow inflation to fade on its own.",
        ],
    },
    "soft_landing": {
        "doc_re": r"\b(soft landing|hard landing|recession|downturn|immaculate disinflation|no recession|labor market)\b",
        "label_a": "soft_landing", "label_b": "hard_landing",
        "fred": ("UNRATE", "level"),
        "pole_a": [
            "The economy is on track for a soft landing, with inflation easing without a recession.",
            "Growth and the labor market can stay resilient while inflation falls.",
            "A recession is not necessary to bring inflation back to target.",
            "Disinflation is proceeding without a significant rise in unemployment.",
            "The Fed can tighten policy without triggering a downturn.",
            "We expect a soft landing as the economy cools gradually.",
        ],
        "pole_b": [
            "Bringing inflation down will require a recession.",
            "A hard landing is increasingly likely as rate hikes bite.",
            "Unemployment must rise substantially to defeat inflation.",
            "The economy is headed for a downturn under tight monetary policy.",
            "A recession is the necessary cost of restoring price stability.",
            "The tightening cycle will end in a hard landing and job losses.",
        ],
        "test_a": [
            "The labor market stayed strong even as inflation cooled, pointing to a soft landing.",
            "Falling inflation alongside steady growth suggests the economy avoids recession.",
            "Policy tightening has slowed inflation without derailing the expansion.",
        ],
        "test_b": [
            "Rising layoffs and weakening demand signal a recession is coming.",
            "The lagged effects of rate hikes will push the economy into a downturn.",
            "Only a sharp rise in unemployment will fully tame inflation.",
        ],
    },
}


def _unit(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.where(n == 0, 1.0, n)


def _discover_axis(dvec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unsupervised contested-axis discovery (Exp 1): 2-component Gaussian mixture
    on PCA-reduced document embeddings; the axis is the difference of the two
    component centroids in embedding space. Deterministic (fixed seed) — no LLM,
    no hand-written poles. Returns (unit axis, projection of docs onto it)."""
    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture

    Xn = _unit(dvec)
    k = int(min(30, Xn.shape[0] - 1, Xn.shape[1]))
    red = PCA(n_components=k, random_state=42).fit_transform(Xn)
    gm = GaussianMixture(n_components=2, covariance_type="full", random_state=42, n_init=5).fit(red)
    lab = gm.predict(red)
    if lab.sum() == 0 or lab.sum() == len(lab):     # degenerate split
        lab = (red[:, 0] > np.median(red[:, 0])).astype(int)
    axis = _unit(Xn[lab == 1].mean(axis=0) - Xn[lab == 0].mean(axis=0))
    return axis, Xn @ axis


def _bimodality(proj: np.ndarray) -> dict:
    """Is the projection genuinely bimodal (a real debate) vs unimodal (consensus)?
    Reports dBIC (1- minus 2-component GMM; positive => two modes preferred),
    Sarle's bimodality coefficient (>0.555 suggests bimodality), and Hartigan's
    dip-test p-value when the ``diptest`` package is available."""
    from sklearn.mixture import GaussianMixture

    x = proj.reshape(-1, 1)
    b1 = GaussianMixture(1, random_state=42).fit(x).bic(x)
    b2 = GaussianMixture(2, random_state=42, n_init=5).fit(x).bic(x)
    from scipy import stats as st
    g = float(st.skew(proj)); ku = float(st.kurtosis(proj, fisher=True)); n = len(proj)
    bc = (g ** 2 + 1) / (ku + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))) if n > 3 else None
    dip_p = None
    try:
        import diptest
        dip_p = round(float(diptest.diptest(proj)[1]), 4)
    except Exception:
        pass
    return {"delta_bic_1_minus_2": round(float(b1 - b2), 1),
            "bimodality_coef": (round(float(bc), 3) if bc is not None else None),
            "dip_p": dip_p}


def _doc_frame(cfg, doc_re: re.Pattern) -> tuple[pd.DataFrame, np.ndarray]:
    clusters = pd.read_parquet(cfg["paths"]["processed_clusters"]).reset_index(drop=True)
    emb = np.load(cfg["paths"]["processed_embeddings"])
    if emb.shape[0] != len(clusters):
        raise RuntimeError("embeddings/clusters row mismatch — re-run cluster stage")
    clusters["published_at"] = pd.to_datetime(clusters["published_at"], utc=True, errors="coerce")
    text = (clusters.get("title").fillna("") + " " + clusters.get("body").fillna(""))
    keep = clusters["published_at"].notna() & text.str.contains(doc_re)
    sub = clusters.iloc[np.nonzero(keep.to_numpy())[0]]
    rows, vecs = [], []
    for aid, g in sub.groupby("article_id"):
        vecs.append(emb[g.index.to_numpy()].mean(axis=0))
        r = g.iloc[0]
        rows.append({"article_id": aid, "published_at": r["published_at"], "source_id": r.get("source_id")})
    return pd.DataFrame(rows), np.asarray(vecs, dtype=np.float32)


def _fred(series: str, transform: str, end: str) -> pd.Series | None:
    try:
        from mnd.ingestion.fred import FredFetcher
        raw = FredFetcher().fetch(series={series: series}, start="2018-01-01", end=end + "-28")
        s = raw[series].astype(float)
        s.index = pd.to_datetime(s.index)
        if transform == "yoy":
            s = (s / s.shift(12) - 1.0) * 100.0
        return s.dropna()
    except Exception as exc:
        log.warning("FRED %s unavailable (%s) — stance series still computed", series, exc)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debate", choices=list(DEBATES), default="inflation")
    ap.add_argument("--start", default="2020-06")
    ap.add_argument("--end", default="2024-06")
    ap.add_argument("--discover", action="store_true",
                    help="also discover the axis unsupervised (GMM+bimodality) and "
                         "compare it to the hand-built axis (Exp 1)")
    args = ap.parse_args()
    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    D = DEBATES[args.debate]
    doc_re = re.compile(D["doc_re"], re.IGNORECASE)

    docs, dvec = _doc_frame(cfg, doc_re)
    win = ((docs["published_at"] >= pd.Timestamp(args.start, tz="UTC")) &
           (docs["published_at"] <= pd.Timestamp(args.end + "-28", tz="UTC")))
    dvec = dvec[np.nonzero(win.to_numpy())[0]]
    docs = docs[win].reset_index(drop=True)
    log.info("[%s] documents in window: %d", args.debate, len(docs))

    import torch
    use_cuda = torch.cuda.is_available()
    ecfg = cfg["embedding"]["primary"]
    embedder = Embedder(
        model_name=ecfg["model"], revision=ecfg.get("revision", "main"),
        instruction_aware=True, instruction_prefix=ecfg.get("instruction_prefix", ""),
        max_seq_len=ecfg.get("max_seq_len", 1024),
        device="cuda" if use_cuda else "cpu", fp16=use_cuda, batch_size=8)
    proj = lambda sents: _unit(embedder.encode(sents, show_progress=False))

    axis = _unit(proj(D["pole_b"]).mean(axis=0) - proj(D["pole_a"]).mean(axis=0))
    dproj = _unit(dvec) @ axis
    center = float(dproj.mean())                  # 0 = average document
    stance = dproj - center

    ta = float((proj(D["test_a"]) @ axis).mean()) - center
    tb = float((proj(D["test_b"]) @ axis).mean()) - center
    face = {
        "label_a": D["label_a"], "label_b": D["label_b"],
        "test_a_mean": round(ta, 4), "test_b_mean": round(tb, 4),
        "separation": round(tb - ta, 4),          # calibration-independent
        "sides_separate": bool(tb > ta),
    }

    # Exp 1: unsupervised axis discovery, validated against the hand-built axis.
    discovery = None
    if args.discover:
        disc_axis, disc_proj = _discover_axis(dvec)
        if float(disc_axis @ axis) < 0:               # orient to the hand-built axis
            disc_axis, disc_proj = -disc_axis, -disc_proj
        dta = float((proj(D["test_a"]) @ disc_axis).mean())
        dtb = float((proj(D["test_b"]) @ disc_axis).mean())
        discovery = {
            "cosine_to_handbuilt": round(float(disc_axis @ axis), 3),
            "bimodality": _bimodality(disc_proj),
            "face_validity_on_discovered": {
                "test_a_mean": round(dta, 4), "test_b_mean": round(dtb, 4),
                "separation": round(dtb - dta, 4), "sides_separate": bool(dtb > dta)},
        }

    docs["stance"] = stance
    docs["month"] = docs["published_at"].dt.to_period("M").dt.to_timestamp()
    monthly = docs.groupby("month").agg(
        stance_mean=("stance", "mean"), n_docs=("stance", "size")).reset_index()

    series, transform = D["fred"]
    fred = _fred(series, transform, args.end)
    corr = None
    if fred is not None:
        m = monthly.set_index("month")
        fr = fred.reindex(m.index.tz_localize(None), method="nearest")
        monthly["fred"] = fr.to_numpy()
        v = monthly["fred"].notna() & monthly["stance_mean"].notna()
        if v.sum() > 3:
            corr = round(float(np.corrcoef(monthly.loc[v, "stance_mean"], monthly.loc[v, "fred"])[0, 1]), 3)

    result = {
        "debate": args.debate, "n_docs": int(len(docs)), "window": [args.start, args.end],
        "face_validity": face, "discovery": discovery,
        "fred_series": series, "stance_fred_correlation": corr,
        "monthly": [
            {"month": str(r["month"].date()), "stance_mean": round(float(r["stance_mean"]), 4),
             "n_docs": int(r["n_docs"]),
             "fred": (round(float(r["fred"]), 2) if "fred" in monthly and pd.notna(r.get("fred")) else None)}
            for _, r in monthly.iterrows()],
    }
    (OUT_DIR / f"{args.debate}.json").write_text(json.dumps(result, indent=2))

    print(f"\n[{args.debate}] {len(docs)} docs, {args.start}..{args.end}  (+ = {D['label_b']}, - = {D['label_a']})")
    print(f"FACE VALIDITY: {D['label_a']}={face['test_a_mean']}  {D['label_b']}={face['test_b_mean']}"
          f"  separation={face['separation']}  sides_separate={face['sides_separate']}")
    if discovery:
        b = discovery["bimodality"]
        print(f"DISCOVERY (unsupervised axis): cosine_to_handbuilt={discovery['cosine_to_handbuilt']}")
        print(f"  bimodal? dBIC={b['delta_bic_1_minus_2']} (>>0 => two modes), "
              f"bimod_coef={b['bimodality_coef']} (>0.555), dip_p={b['dip_p']}")
        fv = discovery["face_validity_on_discovered"]
        print(f"  face-validity on DISCOVERED axis: separation={fv['separation']} "
              f"sides_separate={fv['sides_separate']}")
    print(f"stance<->{series} correlation: {corr}")
    print(f"{'month':<10}{'stance':>9}{'ndocs':>7}{'  '+series:>10}")
    for r in result["monthly"]:
        fr = "  --" if r["fred"] is None else f"{r['fred']:>8.1f}"
        print(f"{r['month']:<10}{r['stance_mean']:>9.3f}{r['n_docs']:>7}{fr}")


if __name__ == "__main__":
    main()
