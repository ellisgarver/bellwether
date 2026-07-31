"""Stance-axis probe — first test of narratives-as-positions (novel method).

Tests the core claim of the debate-structured approach on a debate we already
understand: was the 2021-23 inflation "transitory" or "entrenched"? A narrative
is modelled here not as a topic cluster but as a POSITION on that contested
question, measured with SemAxis (An, Kwak & Ahn 2018) — project each document
onto the axis between two opposing pole framings — and validated against reality
(CPI). If the balance of discourse leans "transitory" in 2021 and tips toward
"entrenched" through 2022 AS CPI STAYS HOT, the position is both measurable and
falsifiable: exactly what a topic model cannot represent.

Deliberately minimal and REVERSIBLE:
  - runs on the EXISTING chunk embeddings (no re-embed of the corpus),
  - uses hand-written economics pole statements (NO LLM in this first test),
  - reads FRED CPI for the reality overlay,
  - writes one JSON; touches nothing in the pipeline.

The only model use is embedding ~16 short pole sentences into the same space as
the documents (same instruction prefix), so pole and document vectors compare.

Usage (RCC; small GPU or CPU for the 16-sentence pole embed):
  export FRED_API_KEY=...    # already set for the markets overlay
  python scripts/experiments/stance_axis.py
  python scripts/experiments/stance_axis.py --start 2020-06 --end 2024-06
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

# The two poles of the 2021-23 inflation debate, in standard economics framing.
# Several paraphrases per side so the pole is a robust centroid, not one framing.
POLE_TRANSITORY = [
    "Inflation is transitory and will fade as supply chains normalize.",
    "Price pressures are temporary, driven by pandemic reopening and base effects.",
    "Supply-side bottlenecks are causing a one-off rise in prices that will subside.",
    "Elevated inflation reflects temporary disruptions and should moderate on its own.",
    "Once supply constraints ease, inflation will return to target.",
    "Higher prices are a temporary side effect of the reopening and will pass.",
    "The spike in inflation is driven by transitory factors, not persistent demand.",
    "Inflation will come back down without aggressive policy tightening.",
]
POLE_ENTRENCHED = [
    "Inflation is becoming entrenched and persistent in the economy.",
    "Price pressures are broadening into wages and services, signaling lasting inflation.",
    "Inflation expectations are un-anchoring, making high inflation self-sustaining.",
    "Demand-driven inflation requires sustained monetary tightening to control.",
    "Inflation is proving sticky and will not fade without aggressive rate hikes.",
    "Second-round wage-price dynamics are embedding inflation in the economy.",
    "Underlying inflation is durable and broad-based, not a temporary blip.",
    "Persistent, demand-side inflation is here to stay absent decisive action.",
]

# Documents that engage the inflation debate at all (whole-word-ish match).
_INFLATION_RE = re.compile(
    r"\b(inflation|consumer price|cpi|pce|price stability|price pressures|"
    r"disinflation|deflation)\b", re.IGNORECASE)


def _doc_frame(cfg) -> tuple[pd.DataFrame, np.ndarray]:
    """Document-level frame + mean-pooled embedding per article (existing vecs)."""
    clusters = pd.read_parquet(cfg["paths"]["processed_clusters"]).reset_index(drop=True)
    emb = np.load(cfg["paths"]["processed_embeddings"])
    if emb.shape[0] != len(clusters):
        raise RuntimeError("embeddings/clusters row mismatch — re-run cluster stage")
    clusters["published_at"] = pd.to_datetime(clusters["published_at"], utc=True, errors="coerce")
    text = (clusters.get("title").fillna("") + " " + clusters.get("body").fillna(""))
    keep = clusters["published_at"].notna() & text.str.contains(_INFLATION_RE)
    idx = np.nonzero(keep.to_numpy())[0]
    sub = clusters.iloc[idx]
    # mean-pool chunk vectors to one vector per article
    rows = []
    vecs = []
    for aid, g in sub.groupby("article_id"):
        gi = g.index.to_numpy()
        v = emb[gi].mean(axis=0)
        vecs.append(v)
        r = g.iloc[0]
        rows.append({"article_id": aid, "published_at": r["published_at"],
                     "source_id": r.get("source_id")})
    return pd.DataFrame(rows), np.asarray(vecs, dtype=np.float32)


def _unit(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.where(n == 0, 1.0, n)


def _cpi_yoy(start: str, end: str) -> pd.Series | None:
    try:
        from mnd.ingestion.fred import FredFetcher
        raw = FredFetcher().fetch(series={"CPIAUCSL": "CPIAUCSL"},
                                  start="2019-01-01", end=end + "-28")
        s = raw["CPIAUCSL"].astype(float)
        s.index = pd.to_datetime(s.index)
        yoy = (s / s.shift(12) - 1.0) * 100.0
        return yoy.dropna()
    except Exception as exc:
        log.warning("CPI overlay unavailable (%s) — stance series still computed", exc)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-06")
    ap.add_argument("--end", default="2024-06")
    args = ap.parse_args()
    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    docs, dvec = _doc_frame(cfg)
    docs = docs[(docs["published_at"] >= pd.Timestamp(args.start, tz="UTC")) &
                (docs["published_at"] <= pd.Timestamp(args.end + "-28", tz="UTC"))].copy()
    dvec = dvec[docs.index.to_numpy()] if len(docs) else dvec
    docs = docs.reset_index(drop=True)
    log.info("Inflation-engaging documents in window: %d", len(docs))

    # Embed poles into the SAME space (same instruction as the corpus). Only 16
    # short sentences, so run wherever: on a GPU node use fp16, but on a CPU node
    # force fp32 (fp16 matmul is unsupported on CPU) so this can skip the A100
    # queue entirely and run on caslake.
    import torch
    use_cuda = torch.cuda.is_available()
    ecfg = cfg["embedding"]["primary"]
    embedder = Embedder(
        model_name=ecfg["model"], revision=ecfg.get("revision", "main"),
        instruction_aware=True, instruction_prefix=ecfg.get("instruction_prefix", ""),
        max_seq_len=ecfg.get("max_seq_len", 1024),
        device="cuda" if use_cuda else "cpu", fp16=use_cuda, batch_size=8)
    pole_t = _unit(embedder.encode(POLE_TRANSITORY, show_progress=False)).mean(axis=0)
    pole_e = _unit(embedder.encode(POLE_ENTRENCHED, show_progress=False)).mean(axis=0)
    axis = _unit(pole_e - pole_t)                 # + = entrenched, - = transitory

    stance = _unit(dvec) @ axis                    # SemAxis projection, [-1, 1]-ish
    docs["stance"] = stance
    docs["month"] = docs["published_at"].dt.to_period("M").dt.to_timestamp()

    monthly = docs.groupby("month").agg(
        stance_mean=("stance", "mean"), n_docs=("stance", "size"),
        share_entrenched=("stance", lambda s: float((s > 0).mean())),
    ).reset_index()

    cpi = _cpi_yoy(args.start, args.end)
    if cpi is not None:
        m = monthly.set_index("month")
        cpi_m = cpi.reindex(m.index.tz_localize(None), method="nearest")
        monthly["cpi_yoy"] = cpi_m.to_numpy()
        valid = monthly["cpi_yoy"].notna() & monthly["stance_mean"].notna()
        corr = float(np.corrcoef(monthly.loc[valid, "stance_mean"],
                                 monthly.loc[valid, "cpi_yoy"])[0, 1]) if valid.sum() > 3 else None
    else:
        corr = None

    result = {
        "n_docs": int(len(docs)),
        "window": [args.start, args.end],
        "stance_cpi_correlation": corr,
        "monthly": [
            {"month": str(r["month"].date()), "stance_mean": round(float(r["stance_mean"]), 4),
             "share_entrenched": round(float(r["share_entrenched"]), 3),
             "n_docs": int(r["n_docs"]),
             "cpi_yoy": (round(float(r["cpi_yoy"]), 2) if "cpi_yoy" in monthly and pd.notna(r.get("cpi_yoy")) else None)}
            for _, r in monthly.iterrows()
        ],
    }
    (OUT_DIR / "inflation.json").write_text(json.dumps(result, indent=2))
    log.info("wrote %s", OUT_DIR / "inflation.json")

    print(f"\nInflation stance axis — {len(docs)} docs, {args.start}..{args.end}")
    print(f"stance<->CPI correlation: {corr}")
    print(f"{'month':<10}{'stance':>9}{'%entr':>7}{'ndocs':>7}{'CPI_yoy':>9}")
    for r in result["monthly"]:
        cpi_str = "  --" if r["cpi_yoy"] is None else f"{r['cpi_yoy']:>8.1f}"
        print(f"{r['month']:<10}{r['stance_mean']:>9.3f}{r['share_entrenched']*100:>6.0f}%"
              f"{r['n_docs']:>7}{cpi_str}")


if __name__ == "__main__":
    main()
