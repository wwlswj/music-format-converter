"""Tests for Windows-safe naming and folder organization."""

from __future__ import annotations

from pathlib import Path

from music_converter.models import ConversionOptions, OverwritePolicy, TrackMetadata
from music_converter.naming import (
    build_output_directory,
    build_output_stem,
    resolve_destination,
    sanitize_component,
)


def test_sanitize_windows_component() -> None:
    """Invalid and reserved Windows names must be made safe."""
    assert sanitize_component('A/B:C*D?E"F<G>H|I', fallback="unknown") == "A_B_C_D_E_F_G_H_I"
    assert sanitize_component("CON", fallback="unknown") == "_CON"
    assert sanitize_component("   ...   ", fallback="未知") == "未知"


def test_default_stem_and_grouping(tmp_path: Path) -> None:
    """Default naming and all-group nesting should follow the specification."""
    metadata = TrackMetadata(
        title="东风破",
        artists=["周杰伦"],
        album="叶惠美",
        genre="华语流行",
    )
    options = ConversionOptions(
        output_dir=tmp_path,
        group_by=("album", "artist", "genre"),
    )
    assert build_output_stem(metadata, options) == "周杰伦 - 东风破"
    expected = tmp_path / "周杰伦" / "华语流行" / "叶惠美"
    assert build_output_directory(tmp_path, metadata, options.group_by) == expected


def test_collision_policies(tmp_path: Path) -> None:
    """Rename, skip, and replace policies should resolve existing files."""
    existing = tmp_path / "song.mp3"
    existing.write_bytes(b"x")
    renamed, skip = resolve_destination(
        tmp_path,
        "song",
        "mp3",
        OverwritePolicy.RENAME,
    )
    assert renamed.name == "song (2).mp3"
    assert not skip
    skipped_path, should_skip = resolve_destination(
        tmp_path,
        "song",
        "mp3",
        OverwritePolicy.SKIP,
    )
    assert skipped_path == existing
    assert should_skip
    replaced_path, should_skip = resolve_destination(
        tmp_path,
        "song",
        "mp3",
        OverwritePolicy.REPLACE,
    )
    assert replaced_path == existing
    assert not should_skip


def test_lrc_only_collision_is_respected(tmp_path: Path) -> None:
    """A sidecar LRC without matching audio must still avoid overwrite."""
    (tmp_path / "song.lrc").write_text("[00:01.00]Hello\n", encoding="utf-8")
    destination, should_skip = resolve_destination(
        tmp_path,
        "song",
        "mp3",
        OverwritePolicy.RENAME,
    )
    assert destination.name == "song (2).mp3"
    assert not should_skip

