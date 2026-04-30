"""Configuration loader.

Loads `config/config.yaml` and exposes typed access. Supports override via
the ``MND_CONFIG_PATH`` environment variable.

The loader is intentionally permissive about extra keys (so the YAML can
evolve without breaking code), but strict about types where they are read.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    """Return the project root, identified by the presence of pyproject.toml."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: assume cwd.
    return Path.cwd()


@lru_cache(maxsize=1)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the master config YAML. Cached for the process lifetime.

    Resolution order:
      1. Explicit ``path`` argument
      2. ``MND_CONFIG_PATH`` environment variable
      3. ``<project_root>/config/config.yaml``
    """
    if path is None:
        path = os.environ.get("MND_CONFIG_PATH")
    if path is None:
        path = _project_root() / "config" / "config.yaml"
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found at {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=4)
def load_yaml(relative_path: str) -> dict[str, Any]:
    """Load any YAML under the project root by relative path."""
    full = _project_root() / relative_path
    if not full.exists():
        raise FileNotFoundError(f"YAML not found at {full}")
    with full.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def project_root() -> Path:
    """Public accessor for the project root."""
    return _project_root()
