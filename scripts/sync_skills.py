"""Synchronize the canonical Agent Skill to Claude Code and optional user roots."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def _sync(source: Path, destination: Path) -> None:
    """Copy the complete canonical skill without deleting unrelated skills."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def _record_project_root(destination: Path, project_root: Path) -> None:
    """Record the source checkout for a user-level skill copy."""
    marker = destination / "scripts" / "project_home.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(project_root), encoding="utf-8")


def main() -> int:
    """Run Skill synchronization."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--user",
        action="store_true",
        help="Also install into user-level ~/.agents/skills and ~/.claude/skills",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    canonical = project_root / "skills" / "music-format-converter"
    if not (canonical / "SKILL.md").is_file():
        raise SystemExit(f"Canonical skill is missing: {canonical}")

    project_agents = project_root / ".agents" / "skills" / "music-format-converter"
    project_claude = project_root / ".claude" / "skills" / "music-format-converter"
    _sync(canonical, project_agents)
    _sync(canonical, project_claude)
    print(f"Synchronized project Skills from: {canonical}")

    if args.user:
        home = Path.home()
        users_agents = home / ".agents" / "skills" / "music-format-converter"
        users_claude = home / ".claude" / "skills" / "music-format-converter"
        _sync(canonical, users_agents)
        _sync(canonical, users_claude)
        _record_project_root(users_agents, project_root)
        _record_project_root(users_claude, project_root)
        print("Synchronized user-level Codex/DeepSeek Harness and Claude skills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

