"""Tests for installing the shared Skill into harness-specific directories."""

from __future__ import annotations

from pathlib import Path

import pytest

from music_converter.config import skill_source_dir
from music_converter.skill_install import SkillInstallError, install_skill, install_skill_targets


def test_ccswitch_repository_path() -> None:
    """The public repository exposes a non-hidden skills directory for CC Switch."""
    root = Path(__file__).resolve().parents[1]
    assert (root / "skills" / "music-format-converter" / "SKILL.md").is_file()


def test_install_codex_skill(tmp_path: Path) -> None:
    """Codex installation should copy all resources and write the client marker."""
    result = install_skill(
        "codex",
        home_root=tmp_path,
        source_dir=skill_source_dir(),
        executable=r"C:\Apps\ShaoLv\music-converter.exe",
    )
    assert result.destination == tmp_path / ".agents" / "skills" / "music-format-converter"
    assert (result.destination / "SKILL.md").is_file()
    assert (result.destination / "scripts" / "run_cli.py").is_file()
    assert (
        result.destination / "scripts" / "app_path.txt"
    ).read_text(encoding="utf-8") == r"C:\Apps\ShaoLv\music-converter.exe"


def test_install_claude_skill(tmp_path: Path) -> None:
    """Claude Code uses its own .claude/skills namespace."""
    result = install_skill(
        "claude",
        home_root=tmp_path,
        source_dir=skill_source_dir(),
        executable="/opt/shao-lv/bin/music-converter",
    )
    assert result.destination == tmp_path / ".claude" / "skills" / "music-format-converter"
    assert (result.destination / "SKILL.md").is_file()


def test_codex_and_deepseek_share_one_destination(tmp_path: Path) -> None:
    """Codex and DeepSeek names resolve to the same current .agents root."""
    results = install_skill_targets(
        ["codex", "deepseek"],
        home_root=tmp_path,
        source_dir=skill_source_dir(),
        executable=r"C:\Apps\ShaoLv\music-converter.exe",
    )
    assert len(results) == 1
    assert results[0].destination == tmp_path / ".agents" / "skills" / "music-format-converter"


def test_unknown_target_is_rejected(tmp_path: Path) -> None:
    """Unsupported harness names must not produce arbitrary directories."""
    with pytest.raises(SkillInstallError):
        install_skill(
            "unknown",
            home_root=tmp_path,
            source_dir=skill_source_dir(),
            executable="music-converter",
        )

