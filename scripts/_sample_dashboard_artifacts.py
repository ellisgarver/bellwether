"""Throwaway: emit a realistic SAMPLE dashboard artifact set for front-end dev.

The live builder (`mnd.dashboard.build_artifacts`) needs fitted dynamics, JEL
assignments, embeddings and overlays — i.e. a full pipeline run. The Astro front
end only needs the *output* JSON, and we want to design it against the full
variety of states the UI must handle before the real corpus lands. So this
fabricates a schema-true artifact set straight from the `artifacts.py`
dataclasses and writes it via the real `write_dashboard_artifacts`, so the bytes
are identical in shape to production. When the real corpus finishes, the live
builder overwrites the same files and the site re-renders unchanged.

Covers: every stage (growth/decay/dormant), in- and out-of-scope JEL, single-
and multi-wave curves, converged and failed fits, emerging and not, and overlays
both present and null.

    python scripts/_sample_dashboard_artifacts.py
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from mnd.dashboard.artifacts import (
    DashboardIndex,
    FitArtifact,
    IndexEntry,
    JELArtifact,
    MarketsArtifact,
    MediaCloudArtifact,
    NarrativeArtifact,
    SeriesArtifact,
    SimilarNarratives,
)
from mnd.dashboard.build_artifacts import write_dashboard_artifacts
from mnd.utils.config import load_config

RNG = np.random.default_rng(42)
OUT = "data/processed/dashboard"

TIMING_NOT_CAUSE = "This shows timing, not cause."
MC_CAPTION = "Broad-press story counts (Media Cloud). Reliable from ~2017."

# Labels carry a date span and a specific identity — not just the top-5 terms.
# Stage now *drives* curve geometry so R0, stage and the plotted curve agree:
#   growth  -> peak late in window, curve still rising at the frontier (R0 > 1)
#   decay   -> peak early, curve falling at the frontier               (R0 < 1)
#   dormant -> low/flat or long-settled, no stable reproduction number (R0 = None)
# (label, jel_code, in_scope, stage, staging_model, start, span_days, freq,
#  overlays, emerging, top_terms)
SPECS = [
    ("Silicon Valley Bank failure (mar 2023)", "G", True, "decay", "sir",
     date(2023, 2, 20), 120, "D", True, False,
     ["svb", "deposits", "bank", "run", "fdic", "uninsured"]),
    ("COVID-19 market crash (feb–apr 2020)", "E", True, "dormant", "logistic",
     date(2020, 2, 10), 200, "D", True, False,
     ["covid", "lockdown", "liquidity", "volatility", "fed", "crash"]),
    ("the 2021–22 inflation surge", "E", True, "decay", "sir",
     date(2022, 1, 1), 540, "W", True, False,
     ["inflation", "cpi", "prices", "core", "energy", "wages"]),
    ("soft-landing optimism (2023–24)", "E", True, "growth", "logistic",
     date(2023, 7, 1), 360, "W", True, True,
     ["soft", "landing", "growth", "labor", "resilient", "disinflation"]),
    ("2013 taper tantrum", "G", True, "dormant", "sir",
     date(2013, 5, 1), 150, "D", False, False,
     ["taper", "tantrum", "treasury", "yields", "bernanke", "qe"]),
    ("2015 China devaluation scare", "F", True, "dormant", "bass",
     date(2015, 8, 1), 130, "D", False, False,
     ["china", "yuan", "devaluation", "pboc", "capital", "outflows"]),
    ("Brexit referendum aftermath (2016)", "F", True, "dormant", "logistic",
     date(2016, 6, 15), 180, "D", False, False,
     ["brexit", "pound", "uk", "referendum", "trade", "sterling"]),
    ("regional-bank contagion (mar–may 2023)", "G", True, "decay", "sir",
     date(2023, 3, 1), 110, "D", True, False,
     ["regional", "first", "republic", "contagion", "deposits", "kre"]),
    ("commercial real-estate stress (2023–25)", "G", True, "growth", "logistic",
     date(2023, 9, 1), 300, "W", True, True,
     ["cre", "office", "vacancy", "refinancing", "maturity", "wall"]),
    ("AI capex and the productivity boom (2024–)", "E", True, "growth", "bass",
     date(2024, 1, 1), 250, "W", False, True,
     ["ai", "capex", "productivity", "datacenter", "investment", "chips"]),
    ("fiscal-deficit sustainability debate (2023–)", "H", True, "growth", "logistic",
     date(2023, 6, 1), 380, "W", False, True,
     ["deficit", "debt", "fiscal", "treasury", "issuance", "sustainability"]),
    ("labor-market cooling (2023–24)", "J", False, "decay", "sir",
     date(2023, 4, 1), 360, "W", False, False,
     ["jobs", "unemployment", "payrolls", "quits", "wage", "jolts"]),
    ("yield-curve normalization (2024–)", "E", True, "growth", "logistic",
     date(2024, 3, 1), 200, "W", True, True,
     ["yield", "curve", "inversion", "2s10s", "steepening", "term"]),
    ("stablecoin and tokenized-deposit risk (2024–)", "G", True, "dormant", "sir",
     date(2021, 11, 1), 60, "D", False, False,
     ["stablecoin", "tokenized", "deposit", "custody", "reserve", "redemption"]),
]

SOURCES = ["federalreserve", "imf", "nber", "bis", "brookings", "piie",
           "voxeu", "cbo", "ofr", "cea"]

# Distinct R0 by stage — these flow into BOTH the stage readout and the staging
# fit, so the badge, the CI and the plotted curve direction can never disagree.
STAGE_R0 = {"growth": 1.9, "decay": 0.55, "dormant": None}
# present mean R0 plus the posterior median and the effective-reproduction
# peak/min over the trajectory. decay's present R0 is sub-1 (fading) yet it
# peaked well above 1 (the explosion); growth is still above 1 now.
STAGE_R0_RANGE = {
    "growth": {"median": 1.84, "peak": 2.15, "min": 1.05},
    "decay": {"median": 0.52, "peak": 2.60, "min": 0.40},
    "dormant": None,
}


# Stage drives where the peak sits and whether the curve is still rising at the
# frontier, so the badge / R0 / plotted direction always agree.
GEOM = {
    "growth":  dict(center=0.92, width=0.34, amp=30.0),  # peak late, still rising
    "decay":   dict(center=0.24, width=0.17, amp=66.0),  # peaked early, falling
    "dormant": dict(center=0.16, width=0.10, amp=80.0),  # narrow spike, long settled
}

# Each lens reads the same event with a different shape (ADR-039) — contrast comes
# from skew: logistic symmetric, SIR sharp-rise/long-decay, Bass early-peak/fat-tail.
LENS_SKEW = {
    "logistic": (0.00, 1.00, 1.00),
    "sir":      (0.05, 0.55, 1.75),
    "bass":     (-0.13, 0.40, 2.30),
}


def _grid(start: date, span: int, freq: str) -> list[date]:
    step = 7 if freq == "W" else 1
    return [start + timedelta(days=i) for i in range(0, span, step)]


def _lens_curve(t: np.ndarray, model: str, center: float, width: float,
                amp: float) -> np.ndarray:
    shift, wl, wr = LENS_SKEW[model]
    z = t - (center + shift)
    left = np.exp(-0.5 * (z / (width * wl)) ** 2)
    right = np.exp(-0.5 * (z / (width * wr)) ** 2)
    return amp * np.where(z < 0, left, right)


def _series_and_curve(stage, staging_model, start, span, freq, sparse):
    grid = _grid(start, span, freq)
    n = len(grid)
    t = np.linspace(0.0, 1.0, n)
    g = dict(GEOM[stage])
    if sparse:
        g["amp"], g["width"] = 6.0, 0.08
    curve = _lens_curve(t, staging_model, g["center"], g["width"], g["amp"])
    noise = RNG.normal(0, 0.12, n) * np.maximum(curve, 1.0)
    observed = np.maximum(0.0, np.round(curve + noise))
    dates = [d.isoformat() for d in grid]
    return dates, observed.tolist(), curve, grid, t, g


def _model_r0(model: str, stage: str):
    if model == "bass" or STAGE_R0[stage] is None:
        return None
    return STAGE_R0[stage]


def _fits(t, g, staging_model, stage, sparse: bool):
    fits = []
    peak_idx = 0 if sparse else int(
        np.argmax(_lens_curve(t, staging_model, g["center"], g["width"], g["amp"]))
    )
    for model in ("logistic", "sir", "bass"):
        if sparse:
            fits.append(FitArtifact(
                model=model, converged=False, aicc=None, r0_mean=None,
                r0_ci=None, peak_time_mean=None, peak_time_ci=None,
                params={}, curve=None,
                failure_reason="insufficient observations for stable fit",
            ))
            continue
        curve = _lens_curve(t, model, g["center"], g["width"], g["amp"])
        r0 = _model_r0(model, stage)
        r0c = (round(r0 - 0.35, 2), round(r0 + 0.45, 2)) if r0 else None
        cmax, csum = float(curve.max()), float(curve.sum())
        params = (
            {"K": round(cmax * 1.1, 2), "r": 0.18, "t0": peak_idx}
            if model == "logistic" else
            {"beta": 0.42, "gamma": 0.2, "N": round(csum, 1)}
            if model == "sir" else
            {"p": 0.012, "q": 0.38, "m": round(csum, 1)}
        )
        # staging model fits best (lowest AICc); the others read a touch worse.
        aicc = round(110.0 + (0.0 if model == staging_model else float(RNG.uniform(8, 30))), 2)
        fits.append(FitArtifact(
            model=model, converged=True, aicc=aicc,
            r0_mean=r0, r0_ci=r0c,
            peak_time_mean=float(peak_idx),
            peak_time_ci=(float(max(0, peak_idx - 6)), float(peak_idx + 6)),
            params=params, curve=curve.tolist(), failure_reason=None,
        ))
    return fits


def _shape_facts(observed, grid):
    arr = np.array(observed)
    total = float(arr.sum())
    peak_idx = int(np.argmax(arr)) if len(arr) else 0
    return {
        "total_volume": total,
        "peak_volume": float(arr.max()) if len(arr) else 0.0,
        "time_to_peak_days": float((grid[peak_idx] - grid[0]).days) if grid else 0.0,
        "wave_count": float(1),
        "active_days": float((arr > 0).sum()),
    }


def _card(label, top_terms, n_articles, dates, peak_date):
    reps = []
    for i in range(min(5, n_articles)):
        src = SOURCES[(hash(label) + i) % len(SOURCES)]
        reps.append({
            "title": f"{label}: {top_terms[i % len(top_terms)].title()} dynamics in focus",
            "source": src,
            "url": f"https://example.org/{src}/{abs(hash(label)) % 99999}-{i}",
            "published_at": dates[min(i * (len(dates)//5 or 1), len(dates)-1)],
            "excerpt": (f"Analysis of {label.lower()} emphasizes "
                        f"{', '.join(top_terms[:3])} as the discourse develops."),
        })
    smix = {}
    for i in range(n_articles):
        s = SOURCES[(hash(label) + i) % len(SOURCES)]
        smix[s] = smix.get(s, 0) + 1
    source_mix = sorted(smix.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "cluster_id": None,  # filled by caller
        "label": label,
        "top_terms": top_terms,
        "n_articles": n_articles,
        "n_chunks": n_articles * 3,
        "date_range": [dates[0], dates[-1]],
        "peak_date": peak_date,
        "source_mix": [list(x) for x in source_mix],
        "representative_articles": reps,
    }


def _mediacloud(grid, curve, reliable_since=2017):
    weekly = grid[::7] if len(grid) > 60 else grid
    dates, counts, ratio = [], [], []
    for d in weekly:
        i = grid.index(d)
        # press lags discourse by ~3 weeks and is noisier
        lag_i = max(0, i - 21)
        base = curve[lag_i] if lag_i < len(curve) else 0.0
        c = int(max(0, base * 90 + RNG.normal(0, 50)))
        if d.year < reliable_since:
            continue
        dates.append(d.isoformat())
        counts.append(c)
        ratio.append(round(c / (base * 90 + 1), 3))
    return MediaCloudArtifact(
        dates=dates, story_count=counts, ratio=ratio,
        reliable_since_year=reliable_since, caption=MC_CAPTION,
    )


def _markets(grid, curve, label):
    # VIX is the canonical overlay + the only series the Granger readout uses
    # (ADR-047); extra series are display-only and not modeled here.
    series, sid = "vix", "VIXCLS"
    weekly = grid[::7] if len(grid) > 60 else grid
    dates, vol, mkt = [], [], []
    for d in weekly:
        i = grid.index(d)
        dates.append(d.isoformat())
        vol.append(float(max(0.0, curve[i] if i < len(curve) else 0.0)))
        mkt.append(round(float(20 + 8 * math.sin(i / 9) + RNG.normal(0, 1.5)), 2))
    verdicts = ["discourse precedes market", "market precedes discourse",
                "no significant precedence", "bidirectional precedence"]
    verdict = verdicts[abs(hash(label)) % 4]
    granger = {
        "series_id": sid, "series_label": series, "max_lag": 4, "alpha": 0.05,
        "caption": TIMING_NOT_CAUSE, "n_obs": len(dates),
        "verdict": verdict,
        "volume_leads_market": {"min_p": 0.012, "best_lag": 2, "significant": True}
        if "discourse" in verdict or "bidirectional" in verdict
        else {"min_p": 0.21, "best_lag": 3, "significant": False},
        "market_leads_volume": {"min_p": 0.03, "best_lag": 1, "significant": True}
        if "market" in verdict or "bidirectional" in verdict
        else {"min_p": 0.34, "best_lag": 2, "significant": False},
    }
    return MarketsArtifact(
        series_id=sid, series_label=series, dates=dates, volume=vol,
        market=mkt, granger=granger, caption=TIMING_NOT_CAUSE,
    )


# 3-D landscape: JEL field sets a centroid, stage nudges within it, noise spreads
# the cloud — so the map shows real structure (fields cluster, stages separate).
JEL_CENTROID = {
    "E": (1.7, 0.3, 0.5), "F": (-1.5, 1.4, -0.4), "G": (0.4, -1.6, 0.9),
    "H": (-0.9, -0.7, -1.5), "J": (1.3, -1.1, -1.2),
}
STAGE_OFFSET = {
    "growth": (0.55, 0.35, 0.25), "decay": (-0.45, -0.25, 0.35),
    "dormant": (0.0, 0.45, -0.45),
}


def main() -> None:
    cfg = load_config()
    narratives: list[NarrativeArtifact] = []
    rows: list[IndexEntry] = []
    positions: dict[int, tuple[float, float, float]] = {}

    for cid, spec in enumerate(SPECS):
        (label, jel_code, in_scope, stage, staging_model, start, span, freq,
         overlays, emerging, top_terms) = spec
        sparse = staging_model == "sir" and "stablecoin" in label.lower()
        dates, observed, curve, grid, t, g = _series_and_curve(
            stage, staging_model, start, span, freq, sparse)
        peak_date = dates[int(np.argmax(observed))] if observed else dates[0]
        n_articles = int(max(3, round(sum(observed))))

        card = _card(label, top_terms, n_articles, dates, peak_date)
        card["cluster_id"] = cid

        r0 = STAGE_R0[stage]
        rng = STAGE_R0_RANGE[stage]
        stage_detail = {
            "model": staging_model, "converged": not sparse,
            "r0_mean": r0,
            # posterior median of the (effective) reproduction number, and the
            # peak/min it reached over the trajectory — peak is the height of the
            # outbreak, min the present floor, so a faded narrative still shows
            # how explosive it once was (see [id].astro table).
            "r0_median": rng["median"] if rng else None,
            "r0_peak": rng["peak"] if rng else None,
            "r0_min": rng["min"] if rng else None,
            "r0_ci_low": round(r0 - 0.3, 2) if r0 else None,
            "r0_ci_high": round(r0 + 0.4, 2) if r0 else None,
            "threshold": cfg["stages"]["growth_min_r0"],
        }

        narratives.append(NarrativeArtifact(
            cluster_id=cid, label=label, stage=stage, card=card,
            volume=SeriesArtifact(dates=dates, values=observed, freq=freq),
            fits=_fits(t, g, staging_model, stage, sparse),
            staging_model=staging_model,
            shape_facts=_shape_facts(observed, grid),
            stage_detail=stage_detail,
            jel=JELArtifact(code=jel_code, in_scope=in_scope,
                            similarity=round(0.55 + RNG.random() * 0.3, 3),
                            runner_up={"E": "G", "F": "E", "G": "E",
                                       "H": "E", "J": "E"}[jel_code],
                            runner_up_gap=round(RNG.random() * 0.1, 3)),
            mediacloud=_mediacloud(grid, curve) if overlays else None,
            markets=_markets(grid, curve, label) if overlays else None,
        ))

        cen = JEL_CENTROID[jel_code]
        off = STAGE_OFFSET[stage]
        positions[cid] = tuple(
            round(float(cen[k] + off[k] + RNG.normal(0, 0.35)), 3) for k in range(3)
        )

        rows.append(IndexEntry(
            cluster_id=cid, label=label, stage=stage, n_articles=n_articles,
            top_terms=top_terms, peak_date=peak_date,
            date_range=(dates[0], dates[-1]), in_scope=in_scope,
            jel_code=jel_code, is_emerging=emerging,
            umap_xy=positions[cid][:2], umap_xyz=positions[cid],
            similar_edges=[],  # filled below
        ))

    # Map edges: 3 nearest neighbors by 3-D distance, weight = 1/(1+dist) (ADR-044).
    for r in rows:
        me = np.array(positions[r.cluster_id])
        dists = sorted(
            ((cid, float(np.linalg.norm(me - np.array(p))))
             for cid, p in positions.items() if cid != r.cluster_id),
            key=lambda kv: kv[1],
        )[:3]
        r.similar_edges = [(cid, round(1.0 / (1.0 + d), 3)) for cid, d in dists]

    # Per-narrative similar panel (three measures) from the same neighbor pool.
    for n in narratives:
        nbrs = [cid for cid, _ in next(r for r in rows
                if r.cluster_id == n.cluster_id).similar_edges]
        n.similar = SimilarNarratives(
            semantic=nbrs,
            lexical=nbrs[:2],
            morphological=nbrs[1:] if len(nbrs) > 1 else [],
        )

    rows.sort(key=lambda e: e.n_articles, reverse=True)
    index = DashboardIndex(
        generated_at="2026-06-14T00:00:00+00:00",
        global_random_seed=int(cfg["reproducibility"]["global_random_seed"]),
        stage_min_r0=float(cfg["stages"]["growth_min_r0"]),
        n_narratives=len(rows), narratives=rows,
    )

    out = write_dashboard_artifacts(index, narratives, OUT)
    print(f"wrote {len(narratives)} sample narratives + index to {out}")
    print(f"  emerging: {sum(1 for r in rows if r.is_emerging)}  | "
          f"out-of-scope: {sum(1 for r in rows if not r.in_scope)}  | "
          f"with overlays: {sum(1 for n in narratives if n.markets)}")


if __name__ == "__main__":
    main()
