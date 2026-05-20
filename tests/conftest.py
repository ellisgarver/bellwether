"""Shared pytest setup.

Loads ``.env`` automatically so integration tests see the API keys
(``GOVINFO_API_KEY``, ``MEDIACLOUD_API_KEY``, ``FRED_API_KEY``) that the
production pipeline gets via ``load_dotenv()`` in ``scripts/run_pipeline.py``.

Without this, integration tests run with whatever the calling shell exports
— which on RCC is usually nothing, causing CEA tests to fall through to the
DEMO_KEY rate-limited path. Loading the .env here once at collection time
fixes that for every test invocation, no matter how it's launched.
"""
from __future__ import annotations

from pathlib import Path


def _load_dotenv_if_present() -> None:
    """Load <repo_root>/.env into os.environ if it exists.

    Silently noop if either dotenv or .env are missing — tests still run,
    they just see whatever environment the shell provides.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_dotenv_if_present()
