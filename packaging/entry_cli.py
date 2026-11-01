"""PyInstaller entry point for the command-line interface."""

from __future__ import annotations

from music_converter.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

