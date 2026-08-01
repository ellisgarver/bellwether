"""Reality-responsiveness fit — the novel dynamics measurable (Exp 2).

Fits the tractable moment-core of the driven-narrative model to a debate's
monthly stance series s(t) and its realized reality field h(t):

    s(t) = c + phi * s(t-1) + lam * h(t) + eps

  phi  — persistence / stubbornness. An AR(1) coefficient, so it is DIMENSIONLESS
         and gauge-invariant (unchanged if the stance axis is rescaled): the
         fraction of last month's position that carries over.
  1-phi — the *capitulation rate*: how fast the narrative adjusts toward reality
         each month. Also gauge-invariant. This is the headline number.
  lam  — contemporaneous pull of realized data toward the reality-consistent
         pole. Scale-DEPENDENT (units of stance / field), so it is reported but
         the invariant summary is the standardized/long-run form.
  lam/(1-phi) — long-run reality pass-through.

Validated against an AR(1) NULL (no field): an F-test asks whether realized data
adds explanatory power over pure persistence. If the field matters AND phi is
high, we have measured a narrative that tracks reality but resists it — the
ratchet-and-stick we observed for inflation, now quantified.

Pure statistics on the existing stance_axis JSON — no embeddings, no compute; runs
on a login node in a second.

Usage:
  python scripts/experiments/narrative_dynamics.py --debate inflation
  python scripts/experiments/narrative_dynamics.py --debate inflation --target 2.0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

IN_DIR = Path("data/experiments/stance_axis")


def _ols(X: np.ndarray, y: np.ndarray):
    XtXi = np.linalg.inv(X.T @ X)
    beta = XtXi @ X.T @ y
    resid = y - X @ beta
    n, k = X.shape
    dof = n - k
    rss = float(resid @ resid)
    sigma2 = rss / dof
    se = np.sqrt(np.maximum(np.diag(sigma2 * XtXi), 0.0))
    t = beta / se
    p = 2 * stats.t.sf(np.abs(t), dof)
    tss = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - rss / tss if tss > 0 else 0.0
    return {"beta": beta, "se": se, "t": t, "p": p, "r2": r2, "rss": rss, "n": n, "k": k}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debate", default="inflation")
    ap.add_argument("--target", type=float, default=2.0,
                    help="reality-field reference (e.g. 2%% inflation target); field = fred - target")
    ap.add_argument("--surrogate", action="store_true",
                    help="circular-shift surrogate test: is the field's TIMING special, "
                         "or would any time-shift of an equally-structured field do as well?")
    ap.add_argument("--field", choices=["level", "cumexcess", "surprise"], default="level",
                    help="reality-field spec: level (fred-target), cumexcess (running sum of "
                         "excess = evidence a mean-reversion prediction failed), surprise (delta fred)")
    args = ap.parse_args()

    d = json.loads((IN_DIR / f"{args.debate}.json").read_text())
    rows = [(r["month"], r["stance_mean"], r["fred"]) for r in d["monthly"]
            if r["stance_mean"] is not None and r["fred"] is not None]
    rows.sort(key=lambda r: r[0])
    s = np.array([r[1] for r in rows], dtype=float)
    excess = np.array([r[2] for r in rows], dtype=float) - args.target
    # Field spec. "cumexcess" is the economically-correct adjudicator for a
    # mean-reversion narrative (transitory): mounting cumulative evidence that
    # inflation did NOT return to target. "surprise" is the monthly change.
    if args.field == "cumexcess":
        h = np.cumsum(excess)
    elif args.field == "surprise":
        h = np.concatenate([[0.0], np.diff(np.array([r[2] for r in rows], dtype=float))])
    else:
        h = excess

    # Align to the AR-X design: y=s[t], regressors s[t-1] and h[t].
    y = s[1:]
    s_lag = s[:-1]
    field = h[1:]
    n = len(y)
    if n < 8:
        print(f"too few monthly points ({n}) for a stable fit"); return

    trend = np.arange(n, dtype=float)
    X_full = np.column_stack([np.ones(n), s_lag, field])
    X_ar = np.column_stack([np.ones(n), s_lag])
    # Spuriousness control: a trending field can beat an AR null just by co-trending.
    # The real test is whether the field adds over a DETERMINISTIC TIME TREND.
    X_trend = np.column_stack([np.ones(n), s_lag, trend])
    X_trend_field = np.column_stack([np.ones(n), s_lag, trend, field])
    full = _ols(X_full, y)
    ar = _ols(X_ar, y)
    tr = _ols(X_trend, y)
    trf = _ols(X_trend_field, y)

    phi = float(full["beta"][1])
    lam = float(full["beta"][2])
    cap = 1.0 - phi                          # capitulation rate (invariant)
    lr = lam / cap if abs(cap) > 1e-6 else float("nan")   # long-run pass-through

    def _ftest(restr, fullm):
        d1 = fullm["k"] - restr["k"]; d2 = fullm["n"] - fullm["k"]
        Fv = ((restr["rss"] - fullm["rss"]) / d1) / (fullm["rss"] / d2)
        return float(Fv), float(stats.f.sf(Fv, d1, d2))

    # does the field add over AR(1)?  (can be spurious if the field trends)
    F, F_p = _ftest(ar, full)
    # THE honest test: does the field add over AR(1) + a linear time trend?
    F_tr, F_tr_p = _ftest(tr, trf)

    result = {
        "debate": args.debate, "n_months": n, "target": args.target,
        "persistence_phi": round(phi, 4), "phi_p": round(float(full["p"][1]), 4),
        "capitulation_rate_1_minus_phi": round(cap, 4),
        "reality_lambda": round(lam, 5), "lambda_p": round(float(full["p"][2]), 4),
        "long_run_passthrough": round(lr, 5),
        "r2_full": round(full["r2"], 4), "r2_ar_null": round(ar["r2"], 4),
        "field_adds_over_ar_F": round(float(F), 3), "field_adds_over_ar_p": round(F_p, 5),
        "r2_trend_null": round(tr["r2"], 4), "r2_trend_plus_field": round(trf["r2"], 4),
        "field_adds_over_TREND_F": round(float(F_tr), 3), "field_adds_over_TREND_p": round(F_tr_p, 5),
    }
    (IN_DIR / f"{args.debate}_dynamics.json").write_text(json.dumps(result, indent=2))

    print(f"\n[{args.debate}] reality-responsiveness fit  (n={n} months)")
    print(f"  persistence phi          = {result['persistence_phi']}  (p={result['phi_p']})   [stubbornness; ~1 = very sticky]")
    print(f"  capitulation rate 1-phi  = {result['capitulation_rate_1_minus_phi']}   [per-month adjustment toward reality; INVARIANT]")
    print(f"  reality response lambda  = {result['reality_lambda']}  (p={result['lambda_p']})")
    print(f"  long-run passthrough     = {result['long_run_passthrough']}")
    print(f"  fit R^2 = {result['r2_full']}  vs AR(1) null R^2 = {result['r2_ar_null']}")
    print(f"  field adds over AR(1)?         F={result['field_adds_over_ar_F']}  p={result['field_adds_over_ar_p']}")
    print(f"  field adds over AR(1)+TREND?   F={result['field_adds_over_TREND_F']}  p={result['field_adds_over_TREND_p']}"
          f"   (R^2 trend={result['r2_trend_null']} -> +field={result['r2_trend_plus_field']})")
    real = result["field_adds_over_TREND_p"] < 0.05
    print(f"  -> {'REAL: field beats a plain time trend (not spurious co-trending)' if real else 'SPURIOUS: a plain time trend explains it just as well'}")

    if args.surrogate:
        # Detrend the field; the trend-controlled test is exactly whether the
        # field's detrended fluctuations add over [1, s_lag, trend]. Circularly
        # shift those fluctuations (preserving their autocorrelation) and see how
        # often a shifted copy matches the true alignment. Exhaustive => exact p.
        Xt = np.column_stack([np.ones(n), trend])
        r = field - Xt @ (np.linalg.inv(Xt.T @ Xt) @ Xt.T @ field)
        base = _ols(np.column_stack([np.ones(n), s_lag, trend]), y)
        F_obs, _ = _ftest(base, _ols(np.column_stack([np.ones(n), s_lag, trend, r]), y))
        Fs = []
        for k in range(1, n):
            rk = np.roll(r, k)
            Fk, _ = _ftest(base, _ols(np.column_stack([np.ones(n), s_lag, trend, rk]), y))
            Fs.append(Fk)
        Fs = np.array(Fs)
        p_emp = (1 + int((Fs >= F_obs).sum())) / (len(Fs) + 1)
        print(f"  SURROGATE (circular-shift null, {len(Fs)} shifts):")
        print(f"    observed F={F_obs:.2f}  vs surrogate F median={np.median(Fs):.2f} max={Fs.max():.2f}")
        print(f"    empirical p = {p_emp:.4f}  -> "
              f"{'REAL: true timing beats shifted copies' if p_emp < 0.05 else 'ARTIFACT: shifts match it, timing not special'}")


if __name__ == "__main__":
    main()
