"""Install the shared music converter Skill for supported agent harnesses."""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from music_converter.config import app_data_dir, application_root, is_frozen, skill_source_dir

SKILL_NAME = "music-format-converter"
SUPPORTED_TARGETS = {"codex", "deepseek", "claude"}


class SkillInstallError(RuntimeError):
    """Raised when a Skill cannot be safely installed."""


@dataclass(slots=True)
class SkillInstallResult:
    """Result of installing the Skill for one harness."""

    target: str
    destination: Path
    backup: Path | None = None


def _destination(target: str, *, scope: str, home_root: Path, project_root: Path) -> Path:
    """Resolve the native Skill destination for one harness."""
    if target not in SUPPORTED_TARGETS:
        raise SkillInstallError(f"不支持的 Skill 目标：{target}")
    if scope not in {"user", "project"}:
        raise SkillInstallError(f"不支持的安装范围：{scope}")
    base = home_root if scope == "user" else project_root
    if target == "claude":
        return base / ".claude" / "skills" / SKILL_NAME
    return base / ".agents" / "skills" / SKILL_NAME


def _cli_marker() -> str:
    """Return a stable client path to embed into the installed Skill."""
    executable = Path(sys.executable).resolve()
    if executable.name.casefold() in {"music-converter", "music-converter.exe"}:
        return str(executable)
    if is_frozen():
        candidates = [
            application_root() / "music-converter.exe",
            application_root() / "music-converter",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return str(application_root())


def install_skill(
    target: str,
    *,
    scope: str = "user",
    home_root: Path | None = None,
    project_root: Path | None = None,
    source_dir: Path | None = None,
    executable: str | None = None,
) -> SkillInstallResult:
    """Copy the canonical Skill to a harness and record client discovery metadata."""
    home = (home_root or Path.home()).expanduser().resolve()
    project = (project_root or Path.cwd()).expanduser().resolve()
    source = (source_dir or skill_source_dir()).resolve()
    if not (source / "SKILL.md").is_file():
        raise SkillInstallError(f"Skill 源目录不完整：{source}")

    destination = _destination(target, scope=scope, home_root=home, project_root=project)
    destination.parent.mkdir(parents=True, exist_ok=True)
    is_junction = getattr(destination, "is_junction", lambda: False)
    if destination.is_symlink() or is_junction():
        raise SkillInstallError(
            "目标 Skill 是符号链接，可能由 CC Switch 或其他管理器托管；"
            "请先在对应管理器中卸载。"
        )

    staging = Path(
        tempfile.mkdtemp(prefix=f".{SKILL_NAME}-", dir=destination.parent)
    ) / SKILL_NAME
    backup: Path | None = None
    try:
        shutil.copytree(source, staging)
        scripts = staging / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "app_path.txt").write_text(
            executable or _cli_marker(),
            encoding="utf-8",
        )

        if destination.exists():
            backup_root = app_data_dir() / "skill-backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = backup_root / f"{SKILL_NAME}-{target}-{timestamp}"
            shutil.move(str(destination), str(backup))

        staging.replace(destination)
    except Exception as exc:
        if backup and backup.exists() and not destination.exists():
            shutil.move(str(backup), str(destination))
        raise SkillInstallError(f"安装 {target} Skill 失败：{exc}") from exc
    finally:
        staging_parent = staging.parent
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if staging_parent.exists():
            shutil.rmtree(staging_parent, ignore_errors=True)

    return SkillInstallResult(
        target=target,
        destination=destination,
        backup=backup,
    )


def install_skill_targets(
    targets: list[str],
    *,
    scope: str = "user",
    home_root: Path | None = None,
    project_root: Path | None = None,
    source_dir: Path | None = None,
    executable: str | None = None,
) -> list[SkillInstallResult]:
    """Install one or more harness targets, de-duplicating shared paths."""
    if "all" in targets:
        targets = ["codex", "deepseek", "claude"]
    seen: set[Path] = set()
    results: list[SkillInstallResult] = []
    for target in dict.fromkeys(targets):
        destination = _destination(
            target,
            scope=scope,
            home_root=(home_root or Path.home()).expanduser().resolve(),
            project_root=(project_root or Path.cwd()).expanduser().resolve(),
        )
        if destination in seen:
            continue
        results.append(
            install_skill(
                target,
                scope=scope,
                home_root=home_root,
                project_root=project_root,
                source_dir=source_dir,
                executable=executable,
            )
        )
        seen.add(destination)
    return results


def result_payload(results: list[SkillInstallResult]) -> list[dict[str, str | None]]:
    """Serialize installation results for CLI output."""
    return [
        {
            "target": item.target,
            "destination": str(item.destination),
            "backup": str(item.backup) if item.backup else None,
        }
        for item in results
    ]

