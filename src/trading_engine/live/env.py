"""Minimal .env loader.

Keys live in a gitignored `.env` at the repo root rather than in shell exports,
so they stay out of shell history and off the command line. Existing
environment variables always win, so an export can still override the file.
"""

from __future__ import annotations

import os
from pathlib import Path

_loaded = False


def _repo_root() -> Path:
    # src/trading_engine/live/env.py -> repo root is four levels up
    return Path(__file__).resolve().parents[3]


def load_env_file(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from `.env` into os.environ (once per process)."""
    global _loaded
    if _loaded and path is None:
        return
    target = path or _repo_root() / ".env"
    if path is None:
        _loaded = True
    if not target.is_file():
        return
    for raw in target.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
