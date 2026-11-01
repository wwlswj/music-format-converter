"""Launch the Music Format Converter desktop application."""

from __future__ import annotations

import sys
from pathlib import Path


def _add_src_path() -> None:
    """Add the local ``src`` directory when running from a source checkout."""
    project_root = Path(__file__).resolve().parent
    src_dir = project_root / "src"
    if src_dir.is_dir():
        sys.path.insert(0, str(src_dir))


def main() -> int:
    """Start the PySide6 application."""
    _add_src_path()
    from music_converter.ui.main_window import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())

