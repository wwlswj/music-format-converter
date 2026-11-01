"""Create the CC Switch-compatible Skill ZIP release asset."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> int:
    """Package the canonical Skill directory with a stable top-level folder."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    source = root / "skills" / "music-format-converter"
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

