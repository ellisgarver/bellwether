#!/usr/bin/env python
"""A/B the narrative-naming backends (ADR-056/061): open local model vs paid Claude.

Reads a sample of the baked dashboard artifacts, rebuilds each cluster's naming
input from its central representative panel, and generates a title + description
with both backends side by side so a human can pick. Bypasses the name cache
(calls the namer directly), so this never writes to data/naming_cache/.

Run on RCC after the analyze re-fit (needs the artifacts with central_articles):
    ANTHROPIC_API_KEY=... python scripts/naming_ab.py --n 12
    python scripts/naming_ab.py --n 12 --backends local      # open model only
"""
from __future__ import annotations

import argparse
import glob
import json
import textwrap
from pathlib import Path

from mnd.dashboard.naming import (
    _SCHEMA,
    _SYSTEM,
    AnthropicNamer,
    LocalHFNamer,
    NamingInput,
    _build_user,
)
from mnd.utils.config import load_config


def _input_from_artifact(nj: dict) -> NamingInput:
    card = nj["card"]
    central = card.get("central_articles") or card.get("representative_articles") or []
    return NamingInput(
        cluster_id=int(nj["cluster_id"]),
        terms=card.get("top_terms", []),
        excerpts=[a["excerpt"] for a in central if a.get("excerpt")],
        date_range=tuple(card["date_range"]) if card.get("date_range") else None,
        sources=[s for s, _ in card.get("source_mix", [])[:4]],
    )


def _sample(data_dir: Path, n: int) -> list[NamingInput]:
    files = sorted(glob.glob(str(data_dir / "narrative_*.json")))
    # spread the sample across the catalog rather than taking the first n
    step = max(1, len(files) // n)
    picked = files[::step][:n]
    return [_input_from_artifact(json.load(open(f))) for f in picked]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--data-dir", default="data/processed/dashboard")
    ap.add_argument("--backends", nargs="+", default=["local", "anthropic"])
    args = ap.parse_args()

    cfg = load_config()
    nc = cfg["display"]["naming"]
    title_words = int(nc.get("max_title_words", 7))
    inputs = _sample(Path(args.data_dir), args.n)
    print(f"A/B naming on {len(inputs)} narratives — backends: {', '.join(args.backends)}\n")

    clients = {}
    for b in args.backends:
        try:
            clients[b] = (LocalHFNamer if b == "local" else AnthropicNamer).from_config(cfg)
        except Exception as exc:  # noqa: BLE001
            print(f"[skip {b}] could not build client: {exc}\n")

    for inp in inputs:
        print("=" * 88)
        print(f"cluster {inp.cluster_id}  |  terms: {', '.join(inp.terms[:8])}")
        for b, client in clients.items():
            try:
                d = client.name_cluster(_SYSTEM, _build_user(inp, title_words), _SCHEMA)
                title, desc = str(d.get("title", "")).strip(), str(d.get("description", "")).strip()
            except Exception as exc:  # noqa: BLE001
                title, desc = "<error>", str(exc)
            print(f"\n  [{b}] {title}")
            for line in textwrap.wrap(desc, width=84):
                print(f"      {line}")
        print()


if __name__ == "__main__":
    main()
