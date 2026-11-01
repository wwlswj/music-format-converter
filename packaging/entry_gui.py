"""PyInstaller entry point for the desktop application."""

from __future__ import annotations

from music_converter.ui.main_window import main

if __name__ == "__main__":
    raise SystemExit(main())

