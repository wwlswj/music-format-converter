"""Application paths and persisted configuration helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

APP_NAME = "MusicFormatConverter"


def _is_writable_directory(path: Path) -> bool:
    """Verify write permission instead of assuming a created directory is usable."""
    try:
        with tempfile.NamedTemporaryFile(prefix=".write-test-", dir=path, delete=True):
            return True
    except OSError:
        return False


def app_data_dir() -> Path:
    """Return a writable per-user directory for caches and logs."""
    override = os.environ.get("MUSIC_CONVERTER_DATA_DIR")
    if override:
        base = Path(override).expanduser()
    else:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) / APP_NAME if appdata else Path.home() / f".{APP_NAME.lower()}"
    try:
        base.mkdir(parents=True, exist_ok=True)
        if not _is_writable_directory(base):
            raise PermissionError(f"数据目录不可写：{base}")
    except OSError:
        base = Path(__file__).resolve().parents[2] / ".music-converter-data"
        base.mkdir(parents=True, exist_ok=True)
        if not _is_writable_directory(base):
            base = Path(tempfile.gettempdir()) / APP_NAME
            base.mkdir(parents=True, exist_ok=True)
    return base


def lyrics_cache_path() -> Path:
    """Return the SQLite lyric cache location."""
    cache_dir = app_data_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "lyrics.sqlite3"


def log_dir() -> Path:
    """Return the local log directory."""
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path

