"""Application paths and persisted configuration helpers."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "MusicFormatConverter"


def is_frozen() -> bool:
    """Return whether the application is running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def application_root() -> Path:
    """Return the source checkout or installed application directory."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Return the root containing bundled read-only resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", application_root())).resolve()
    return application_root()


def skill_source_dir() -> Path:
    """Return the canonical Skill directory bundled with source or binaries."""
    candidates = [
        resource_root() / "skills" / "music-format-converter",
        application_root() / "skills" / "music-format-converter",
    ]
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate
    return candidates[0]


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
        base = application_root() / ".music-converter-data"
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

