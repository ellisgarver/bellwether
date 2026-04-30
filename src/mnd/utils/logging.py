"""Logging configuration for the project.

Use ``get_logger(__name__)`` rather than ``logging.getLogger`` directly so
that all modules share a consistent format and level.
"""
from __future__ import annotations

import logging
import os
import sys
from logging import Logger

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    level_name = os.environ.get("MND_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    root = logging.getLogger("mnd")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> Logger:
    """Get a module-scoped logger under the ``mnd`` namespace."""
    _configure_root()
    if not name.startswith("mnd"):
        name = f"mnd.{name}"
    return logging.getLogger(name)
