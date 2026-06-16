#!/usr/bin/env python3
"""Coverage-shape verification for a single ingested source.

Born from the 2026-06-04 BIS miss: a job that "didn't fail" and showed all
years present was still undercapturing early years ~10x, because one series
(``/review/`` speeches) was PDF-only in the pre-2014 sitemap and silently
skipped. A year-TOTAL histogram hid it; a year x document_type pivot exposes it
(speech=1 in 2010 vs 765 in 2014). This is the standing captured-side check in
the verification standard: shape, not presence.

It does NOT fetch the source's ground-truth inventory — that is the
source-specific check (enumerate the source's own sitemap/CDX/listing by series
and diff), run separately. Here we surface the bug signatures that live in the
captured data itself:

  CLIFF  a >=Nx jump in one series between adjacent active years
         -> likely a format / URL-scheme change the ingestor doesn't handle
            (BIS pdf->htm at 2014).
  GAP    a series at zero inside its own active span
         -> the series dropped out for that year.
  DUP    many URLs sharing a trailing slug
         -> dedup bug, e.g. the same article under two URL schemes
            (PIIE flat-slug + /YYYY/ at the 2016 CMS migration).

A clean run is necessary, not sufficient: still confirm against the source's
independent inventory before clearing a source.

Usage (on RCC, from the repo root):
    python scripts/verify_coverage.py bis
    python scripts/verify_coverage.py piie --cliff 5 --min 20
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict

ART_DIR = "data/raw/articles"
_YEAR_RE = re.compile(r"^(19|20)\d\d$")


def load(source: str):
    files = sorted(glob.glob(f"{ART_DIR}/{source}_*.jsonl"))
    if not files:
        sys.exit(f"no JSONL files for source '{source}' under {ART_DIR}/")
    rows = []
    for fp in files:
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return files, rows


def doc_type(rec: dict) -> str:
    rm = rec.get("raw_metadata") or {}
    return rm.get("document_type") or rec.get("section") or "(none)"


def _pctile(sorted_vals: list[int], q: float) -> int:
    """Nearest-rank percentile on a pre-sorted list (q in [0,1])."""
    if not sorted_vals:
        return 0
    i = min(len(sorted_vals) - 1, int(q * (len(sorted_vals) - 1) + 0.5))
    return sorted_vals[i]


def body_report(source: str, files: list[str], rows: list[dict], short: int) -> None:
    """Full-article-content check: empty / short bodies + word distribution,
    broken out by document_type. The shape pivot proves a URL was captured; this
    proves the *text* came with it. A fetch that failed but was stored anyway
    (Finding #2) shows up as a doc_type with a high empty-body share; a listing
    page or truncated extract shows up in the short-body tail. Word counts are
    recomputed from `body` here — the stored `word_count` field is not trusted."""
    by_dtype: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "empty": 0, "short": 0, "words": []}
    )
    empty_total = short_total = 0
    for rec in rows:
        b = by_dtype[doc_type(rec)]
        b["n"] += 1
        body = (rec.get("body") or "").strip()
        if not body:
            b["empty"] += 1
            empty_total += 1
            continue
        w = len(body.split())
        b["words"].append(w)
        if w < short:
            b["short"] += 1
            short_total += 1

    dtypes = sorted(by_dtype)
    w = max([len(d) for d in dtypes] + [13])
    n = len(rows)
    print(f"\n== {source}: body fullness — {n} records across {len(files)} file(s) "
          f"(short < {short} words) ==")
    hdr = (f"{'document_type'.ljust(w)}{'records':>9}{'empty':>8}{'empty%':>8}"
           f"{'short':>7}{'wMin':>7}{'wMed':>8}{'wP90':>8}{'wMax':>8}")
    print(hdr)
    print("-" * len(hdr))
    for d in dtypes:
        b = by_dtype[d]
        ws = sorted(b["words"])
        empty_pct = 100 * b["empty"] / b["n"] if b["n"] else 0.0
        med = ws[len(ws) // 2] if ws else 0
        print(f"{d.ljust(w)}{b['n']:>9}{b['empty']:>8}{empty_pct:>7.1f}%"
              f"{b['short']:>7}{(ws[0] if ws else 0):>7}{med:>8}"
              f"{_pctile(ws, 0.90):>8}{(ws[-1] if ws else 0):>8}")
    epct = 100 * empty_total / n if n else 0.0
    spct = 100 * short_total / n if n else 0.0
    print("-" * len(hdr))
    print(f"{'TOTAL'.ljust(w)}{n:>9}{empty_total:>8}{epct:>7.1f}%{short_total:>7}")

    flags: list[str] = []
    if epct >= 5.0:
        flags.append(f"{epct:.1f}% of records have an EMPTY body "
                     f"({empty_total}/{n}) — likely fetch-failures stored as metadata-only")
    for d in dtypes:
        b = by_dtype[d]
        if b["n"] >= 20 and 100 * b["empty"] / b["n"] >= 20.0:
            flags.append(f"{d}: {100 * b['empty'] / b['n']:.0f}% empty bodies "
                         f"({b['empty']}/{b['n']}) — this series may be PDF-only / "
                         f"behind a fetch path that returns no text")
    if flags:
        print("\nFLAGS (full content is the standard — investigate before clearing):")
        for f in flags:
            print("  ! " + f)
    else:
        print(f"\nno empty/short-body flags ({epct:.1f}% empty, {spct:.1f}% short). "
              f"Bodies are present; confirm shape with the default (non-body) run too.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="source_id, e.g. bis (globs data/raw/articles/<source>_*.jsonl)")
    ap.add_argument("--cliff", type=float, default=5.0,
                    help="adjacent-year ratio in one series that triggers a CLIFF flag (default 5)")
    ap.add_argument("--min", type=int, default=20,
                    help="ignore cliffs/gaps where the larger side is below this count (default 20)")
    ap.add_argument("--body", action="store_true",
                    help="body-fullness mode: empty/short bodies + word distribution per document_type")
    ap.add_argument("--short", type=int, default=50,
                    help="word count below which a non-empty body is flagged 'short' (default 50)")
    args = ap.parse_args()

    files, rows = load(args.source)

    if args.body:
        body_report(args.source, files, rows, args.short)
        return

    pivot: dict[str, Counter] = defaultdict(Counter)  # pivot[document_type][year]
    slug: Counter = Counter()
    scheme: Counter = Counter()
    bad_date = 0
    for rec in rows:
        yr = (rec.get("published_at") or "")[:4]
        if not _YEAR_RE.match(yr):
            bad_date += 1
            continue
        pivot[doc_type(rec)][yr] += 1
        u = (rec.get("url") or "").rstrip("/")
        slug[u.rsplit("/", 1)[-1]] += 1
        scheme["YYYY" if re.search(r"/(19|20)\d{2}/", u) else "flat"] += 1

    years = sorted({y for c in pivot.values() for y in c})
    dtypes = sorted(pivot)
    if not years:
        sys.exit(f"{args.source}: no records with a parseable published_at year "
                 f"({bad_date} unparseable).")

    w = max([len(d) for d in dtypes] + [13])
    print(f"\n== {args.source}: {len(rows)} records across {len(files)} file(s) ==")
    hdr = "document_type".ljust(w) + "".join(y[2:].rjust(6) for y in years) + "   total"
    print(hdr)
    print("-" * len(hdr))
    total = Counter()
    for d in dtypes:
        c = pivot[d]
        total.update(c)
        line = d.ljust(w) + "".join((str(c[y]) if c[y] else ".").rjust(6) for y in years)
        print(line + str(sum(c.values())).rjust(8))
    print("TOTAL".ljust(w) + "".join(str(total[y]).rjust(6) for y in years)
          + str(sum(total.values())).rjust(8))

    flags: list[str] = []
    for d in dtypes:
        c = pivot[d]
        nz = [y for y in years if c[y] > 0]
        span = [y for y in years if nz[0] <= y <= nz[-1]]
        for i in range(1, len(span)):
            y0, y1 = span[i - 1], span[i]
            a, b = c[y0], c[y1]
            if a == 0 or b == 0:
                live = max(a, b)
                if live >= args.min:
                    zero_year = y1 if b == 0 else y0
                    flags.append(f"GAP    {d}: {zero_year}=0 inside active span "
                                 f"(adjacent year={live})")
                continue
            ratio = max(a, b) / min(a, b)
            if ratio >= args.cliff and max(a, b) >= args.min:
                flags.append(f"CLIFF  {d}: {y0}={a} -> {y1}={b} ({ratio:.1f}x)")

    dups = sum(1 for v in slug.values() if v > 1)
    if dups:
        top = ", ".join(f"{s}({v})" for s, v in slug.most_common(5) if v > 1)
        flags.append(f"DUP    {dups} trailing-slugs repeat across URLs; top: {top}")

    print()
    if scheme.get("flat") and scheme.get("YYYY"):
        print(f"url scheme split: flat={scheme['flat']}  /YYYY/={scheme['YYYY']}")
    if bad_date:
        print(f"records dropped from pivot (unparseable published_at year): {bad_date}")
    if flags:
        print("\nFLAGS (investigate against the source's own inventory — check #1):")
        for f in flags:
            print("  ! " + f)
    else:
        print("\nno shape flags. NOT sufficient on its own — still diff against the "
              "source's independent inventory before clearing.")


if __name__ == "__main__":
    main()
