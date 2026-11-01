"""Run the project CLI from a repository or installed Skill location."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _project_command(project_root: Path, arguments: list[str]) -> list[str] | None:
    """Build a command when ``project_root`` contains this source checkout."""
    python = project_root / ".venv" / "Scripts" / "python.exe"
    source = project_root / "src" / "music_converter"
    if python.is_file() and source.is_dir():
        return [str(python), "-m", "music_converter", *arguments]
    return None


def _path_command(path: Path, arguments: list[str]) -> list[str] | None:
    """Turn a recorded executable or application directory into a command."""
    expanded = path.expanduser().resolve()
    if expanded.is_file():
        return [str(expanded), *arguments]
    project_command = _project_command(expanded, arguments)
    if project_command:
        return project_command
    for name in ("music-converter.exe", "music-converter"):
        candidate = expanded / name
        if candidate.is_file():
            return [str(candidate), *arguments]
    return None


def locate_command(arguments: list[str]) -> list[str] | None:
    """Locate the converter without relying on shell interpolation."""
    for marker_name in ("app_path.txt", "project_home.txt"):
        marker = Path(__file__).with_name(marker_name)
        if marker.is_file():
            try:
                recorded = marker.read_text(encoding="utf-8").strip()
            except OSError:
                recorded = ""
            if recorded:
                candidate = _path_command(Path(recorded), arguments)
                if candidate:
                    return candidate

    configured = os.environ.get("MUSIC_CONVERTER_HOME")
    if configured:
        candidate = _path_command(Path(configured), arguments)
        if candidate:
            return candidate

    script = Path(__file__).resolve()
    for parent in script.parents:
        candidate = _project_command(parent, arguments)
        if candidate:
            return candidate

    home = Path.home()
    local_app_data = os.environ.get("LOCALAPPDATA")
    known_paths = []
    if local_app_data:
        known_paths.append(
            Path(local_app_data) / "Programs" / "ShaoLv" / "music-converter.exe"
        )
    known_paths.extend(
        [
            home / "AppData" / "Local" / "Programs" / "ShaoLv" / "music-converter.exe",
            home / ".local" / "share" / "shao-lv" / "bin" / "music-converter",
            home / ".local" / "bin" / "music-converter",
            Path("/opt/shao-lv/bin/music-converter"),
        ]
    )
    for path in known_paths:
        if path.is_file():
            return [str(path), *arguments]

    for command_name in ("music-converter", "music-converter.exe"):
        executable = shutil.which(command_name)
        if executable:
            return [executable, *arguments]
    return None


def main() -> int:
    """Execute the converter and forward its exit code."""
    arguments = sys.argv[1:]
    command = locate_command(arguments)
    if command is None:
        print(
            "找不到 Music Format Converter。请设置 MUSIC_CONVERTER_HOME "
            "或安装项目虚拟环境。",
            file=sys.stderr,
        )
        return 2
    try:
        process = subprocess.run(
            command,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except OSError as exc:
        print(f"无法启动转换器：{exc}", file=sys.stderr)
        return 2
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())

