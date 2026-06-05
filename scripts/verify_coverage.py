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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="source_id, e.g. bis (globs data/raw/articles/<source>_*.jsonl)")
    ap.add_argument("--cliff", type=float, default=5.0,
                    help="adjacent-year ratio in one series that triggers a CLIFF flag (default 5)")
    ap.add_argument("--min", type=int, default=20,
                    help="ignore cliffs/gaps where the larger side is below this count (default 20)")
    args = ap.parse_args()

    files, rows = load(args.source)

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
