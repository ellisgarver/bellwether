"""Pre-flight environment check.

Run this BEFORE any pipeline work to confirm:
  1. Python and core dependencies importable
  2. Config files parse and have the expected schema version
  3. Anchor and fizzled JSONL files are well-formed
  4. FRED API key is set (validation data layer)
  5. Embedding model can be loaded (downloads model weights on first run)

This script does NOT require UChicago library access — that gate is checked
separately. The intent is to surface infrastructure problems before they
cost you a debugging session in the middle of a pipeline run.

Usage:
    python scripts/preflight_check.py
    python scripts/preflight_check.py --skip-embedding   # quick check, no model download
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make src/ importable when run from repo root.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))


def _check(name: str) -> callable:
    def deco(fn):
        fn._check_name = name
        return fn
    return deco


@_check("Python version")
def check_python() -> tuple[bool, str]:
    major, minor = sys.version_info[:2]
    ok = major == 3 and 11 <= minor <= 12
    return ok, f"Python {major}.{minor} ({'OK' if ok else 'requires 3.11–3.12'})"


@_check("Core imports")
def check_imports() -> tuple[bool, str]:
    missing = []
    for pkg in [
        "numpy", "pandas", "yaml", "pydantic", "requests", "bs4",
        "tenacity", "tqdm", "click",
    ]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return not missing, "all core imports OK" if not missing else f"missing: {missing}"


@_check("Config files parse")
def check_configs() -> tuple[bool, str]:
    from mnd.utils.config import load_config, load_yaml
    cfg = load_config()
    wl = load_yaml("config/whitelist.yaml")
    issues = []
    if cfg.get("schema_version") != "2.0.0":
        issues.append(f"config schema_version={cfg.get('schema_version')} (expected 2.0.0 per ADR-019)")
    # Whitelist keys per ADR-020: tier_1_institutional_policy + tier_2_*
    if not wl.get("tier_1_institutional_policy"):
        issues.append("whitelist tier_1_institutional_policy empty")
    if not wl.get("tier_2_academic_analytical"):
        issues.append("whitelist tier_2_academic_analytical empty")
    # ADR-020: topic_filter_keywords.yaml archived; no keyword check at this stage.
    return not issues, "all configs OK" if not issues else "; ".join(issues)


@_check("Anchor JSONL is valid")
def check_anchors() -> tuple[bool, str]:
    repo = Path(__file__).resolve().parent.parent
    path = repo / "data" / "anchors" / "anchor_narratives.jsonl"
    if not path.exists():
        return False, f"missing: {path}"
    n = 0
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                return False, f"invalid JSONL on line {n+1}: {e}"
            for required in ("id", "name", "reference_date", "tolerance_days", "key_terms"):
                if required not in obj:
                    return False, f"anchor {obj.get('id')} missing field {required}"
            n += 1
    return n >= 10, f"{n} anchor narratives loaded"


@_check("FRED API key")
def check_fred() -> tuple[bool, str]:
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return False, "FRED_API_KEY not set in env (see .env.example)"
    # A live API call is the strongest check, but it costs a request and
    # delays preflight; a presence check is sufficient here.
    return True, "FRED_API_KEY present"


@_check("Institutional ingestor importable")
def check_institutional_ingestor() -> tuple[bool, str]:
    try:
        from mnd.ingestion import InstitutionalIngestor
        ing = InstitutionalIngestor()
        n_sub = len(ing._sub_ingestors)
        # Expected 12 active sub-ingestors per ADR-020: Fed, FedRegional,
        # Congressional, IMF, BIS, TreasuryOFR, CBO, CEA, VoxEU, Brookings,
        # PIIE, NBER. (CFR removed, CEA + NBER added.)
        return n_sub == 12, f"InstitutionalIngestor with {n_sub} sub-ingestors"
    except Exception as exc:
        return False, f"failed to instantiate InstitutionalIngestor: {exc}"


@_check("Embedding model loadable")
def check_embedding() -> tuple[bool, str]:
    try:
        from mnd.embedding import Embedder
        emb = Embedder.from_config("primary")
        # Force a tiny encode to verify the model + tokenizer download path.
        _ = emb.encode(["test sentence about inflation"], show_progress=False)
        return True, f"loaded {emb.model_name}, dim={_.shape[1]}"
    except Exception as exc:  # pragma: no cover
        return False, f"failed: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-embedding", action="store_true",
        help="Skip the embedding-model load (saves ~minutes on first run)."
    )
    args = parser.parse_args()

    checks = [check_python, check_imports, check_configs, check_anchors,
              check_fred, check_institutional_ingestor]
    if not args.skip_embedding:
        checks.append(check_embedding)

    print("Pre-flight check\n" + "=" * 60)
    failures = 0
    for fn in checks:
        try:
            ok, msg = fn()
        except Exception as exc:
            ok, msg = False, f"raised {type(exc).__name__}: {exc}"
        sigil = "✓" if ok else "✗"
        print(f"  {sigil}  {fn._check_name:30s}  {msg}")
        if not ok:
            failures += 1
    print("=" * 60)
    print(f"{len(checks) - failures}/{len(checks)} checks passed.")
    if failures:
        print(
            "\nNext steps:\n"
            "  - For missing imports: `pip install -r requirements.txt`\n"
            "  - For missing FRED key: copy .env.example to .env and fill in\n"
            "  - For embedding failure: check internet connectivity to HuggingFace\n"
            "  - For config issues: do not edit locked configs without ADR; see docs/\n"
        )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
