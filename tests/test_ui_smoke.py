"""Offscreen smoke test for the PySide6 window."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from music_converter.media.ffmpeg import ToolPaths
from music_converter.models import JobStatus
from music_converter.ui.main_window import MainWindow
from music_converter.ui.theme import apply_theme


def test_main_window_builds(qapp: QApplication, qtbot, tmp_path: Path) -> None:
    """All four pages should construct and the empty queue state should be visible."""
    apply_theme(qapp)
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.show()
    assert window.page_stack.count() == 4
    assert window.queue_stack.currentIndex() == 0
    assert window.start_button.isEnabled()


def test_window_runs_background_conversion(
    qapp: QApplication,
    qtbot,
    tmp_path: Path,
) -> None:
    """The Qt task lifecycle should update the queue after a real conversion."""
    tools = ToolPaths.discover()
    if not tools.ffmpeg:
        pytest.skip("FFmpeg is not installed")
    source = tmp_path / "界面歌手 - 界面测试.wav"
    generated = subprocess.run(
        [
            str(tools.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=523:duration=1",
            "-c:a",
            "pcm_s16le",
            str(source),
            "-y",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr

    apply_theme(qapp)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.output_edit.setText(str(tmp_path / "output"))
    window.lyrics_check.setChecked(False)
    window._add_paths([source])
    window.show()
    window._start_batch()
    qtbot.waitUntil(lambda: not window.active_tasks, timeout=20_000)
    assert window.queue_entries[0].status is JobStatus.SUCCESS
    assert window.queue_entries[0].result is not None
    assert window.queue_entries[0].result.output_path is not None
    assert window.queue_entries[0].result.output_path.is_file()

