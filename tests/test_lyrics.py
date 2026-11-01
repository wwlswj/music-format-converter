"""Tests for lyric normalization, local files, and matching helpers."""

from __future__ import annotations

from pathlib import Path

from music_converter.lyrics import (
    LyricsCache,
    LyricsResolver,
    has_lrc_timestamps,
    make_unsynced_lrc,
    merge_translated_lyrics,
    normalize_match_text,
    read_lrc_file,
)
from music_converter.models import LyricsResolution, LyricsStatus, TrackMetadata


def test_lrc_detection_and_translation_merge() -> None:
    """Timestamp detection and bilingual merging should preserve timing."""
    original = "[00:01.00]Hello\n[00:02.50]World\n"
    translated = "[00:01.00]你好\n[00:02.50]世界\n"
    assert has_lrc_timestamps(original)
    merged = merge_translated_lyrics(original, translated)
    assert "[00:01.00]Hello / 你好" in merged
    assert "[00:02.50]World / 世界" in merged
    assert not has_lrc_timestamps(make_unsynced_lrc("Line one\nLine two", TrackMetadata()))


def test_normalize_match_text_is_conservative() -> None:
    """Normalization should remove common version noise without destroying Chinese."""
    assert normalize_match_text("Song (Live Remastered)") == "song"
    assert normalize_match_text("东风破（现场版）") in {"东风破现场版", "东风破"}


def test_resolver_uses_local_lrc(tmp_path: Path) -> None:
    """A sibling LRC should be preferred without invoking the network provider."""
    source = tmp_path / "artist - song.mp3"
    source.write_bytes(b"not-real-audio")
    source.with_suffix(".lrc").write_text(
        "[00:01.00]第一句\n[00:02.00]第二句\n",
        encoding="utf-8",
    )
    resolver = LyricsResolver(cache=LyricsCache(tmp_path / "cache.sqlite3"))
    result = resolver.resolve(
        source,
        TrackMetadata(title="Song", artists=["Artist"], duration=3),
        fetch_online=True,
        allow_unsynced=False,
    )
    assert result.status is LyricsStatus.LOCAL_FILE
    assert result.synced
    assert "[00:01.00]第一句" in result.content


def test_cache_restores_enum_status(tmp_path: Path) -> None:
    """Cached JSON records must deserialize into the LyricsStatus enum."""
    cache = LyricsCache(tmp_path / "cache.sqlite3")
    metadata = TrackMetadata(title="Cache Song", artists=["Artist"], duration=90)
    expected = LyricsResolution(
        status=LyricsStatus.ONLINE,
        provider="LRCLIB",
        content="[00:01.00]Cached\n",
        synced=True,
        confidence=0.95,
    )
    cache.set(metadata, expected)
    restored = cache.get(metadata)
    assert restored is not None
    assert restored.status is LyricsStatus.ONLINE
    assert restored.content == expected.content


def test_lrc_reader_supports_gb18030(tmp_path: Path) -> None:
    """Legacy Chinese LRC files should not be silently discarded."""
    path = tmp_path / "legacy.lrc"
    path.write_bytes("[00:01.00]旧编码歌词\n".encode("gb18030"))
    assert "旧编码歌词" in read_lrc_file(path)


def test_local_lrc_is_used_when_online_lookup_is_disabled(tmp_path: Path) -> None:
    """Local sidecars remain available even when network lyrics are disabled."""
    source = tmp_path / "artist - offline.mp3"
    source.write_bytes(b"not-real-audio")
    source.with_suffix(".lrc").write_text(
        "[00:01.00]离线歌词\n",
        encoding="utf-8",
    )
    resolver = LyricsResolver(cache=LyricsCache(tmp_path / "cache.sqlite3"))
    result = resolver.resolve(
        source,
        TrackMetadata(title="Offline", artists=["Artist"], duration=3),
        fetch_online=False,
        allow_unsynced=False,
    )
    assert result.status is LyricsStatus.LOCAL_FILE
    assert "离线歌词" in result.content

