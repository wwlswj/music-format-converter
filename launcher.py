"""Resilient GUI launcher for pythonw.exe.

This entry point catches startup failures that would otherwise disappear
because ``pythonw.exe`` has no console window.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _log_path(project_root: Path) -> Path:
    """Return a writable launcher log path."""
    preferred = os.environ.get("LOCALAPPDATA")
    candidates = [project_root / ".music-converter-data" / "logs"]
    if preferred:
        candidates.append(Path(preferred) / "MusicFormatConverter" / "logs")
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return directory / "launcher.log"
        except OSError:
            continue
    return Path(os.environ.get("TEMP", project_root)) / "MusicFormatConverter-launcher.log"


def _append_log(project_root: Path, message: str) -> None:
    """Write a UTF-8 launcher log without allowing logging failure to mask startup."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    preferred = _log_path(project_root)
    candidates = [preferred, project_root / ".music-converter-data" / "launcher.log"]
    for path in dict.fromkeys(candidates):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{timestamp}] {message.rstrip()}\n")
            return
        except OSError:
            continue


def _show_error(message: str) -> None:
    """Show a native error dialog when no console is available."""
    with contextlib.suppress(Exception):
        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "韶律启动失败",
            0x10,
        )


def main() -> int:
    """Import and run the GUI with startup error reporting."""
    project_root = Path(__file__).resolve().parent
    src_dir = project_root / "src"
    if not src_dir.is_dir():
        message = f"找不到程序源码目录：{src_dir}"
        _append_log(project_root, message)
        _show_error(message)
        return 2

    sys.path.insert(0, str(src_dir))
    _append_log(project_root, "正在启动韶律…")
    try:
        from music_converter.ui.main_window import main as gui_main

        return int(gui_main())
    except BaseException:
        details = traceback.format_exc()
        log_file = _log_path(project_root)
        _append_log(project_root, details)
        _show_error(
            "程序启动失败。\n\n"
            f"{details.splitlines()[-1]}\n\n"
            f"完整错误已写入：\n{log_file}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

