"""Shared pytest configuration."""

from __future__ import annotations

import os
from pathlib import Path


def pytest_configure() -> None:
    """Keep application cache data inside the writable project directory."""
    data_dir = Path(__file__).resolve().parents[1] / ".tmp" / "pytest-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MUSIC_CONVERTER_DATA_DIR"] = str(data_dir)

