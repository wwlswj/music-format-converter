"""Shared domain models for conversion jobs and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SourceKind(StrEnum):
    """Supported source-file families."""

    AUDIO = "audio"
    NCM = "ncm"


class JobStatus(StrEnum):
    """Lifecycle state for one conversion job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class LyricsStatus(StrEnum):
    """Outcome of the lyric resolution stage."""

    NOT_REQUESTED = "not_requested"
    EMBEDDED = "embedded"
    LOCAL_FILE = "local_file"
    ONLINE = "online"
    INSTRUMENTAL = "instrumental"
    PENDING = "pending"
    NOT_FOUND = "not_found"
    ERROR = "error"


class OverwritePolicy(StrEnum):
    """Collision behavior when the destination already exists."""

    RENAME = "rename"
    REPLACE = "replace"
    SKIP = "skip"


@dataclass(slots=True)
class TrackMetadata:
    """Normalized metadata extracted from an audio or NCM source."""

    title: str = ""
    artists: list[str] = field(default_factory=list)
    album: str = ""
    genre: str = ""
    duration: float = 0.0
    bitrate: int = 0
    source_format: str = ""
    source_id: int | None = None
    cover_data: bytes | None = None
    cover_mime: str = ""
    embedded_lyrics: str = ""
    translated_lyrics: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def artist_text(self) -> str:
        """Return a display-friendly artist string."""
        return ", ".join(part for part in self.artists if part).strip()

    def merged_with(self, other: TrackMetadata) -> TrackMetadata:
        """Return a copy where non-empty values from ``other`` take precedence."""
        return TrackMetadata(
            title=other.title or self.title,
            artists=other.artists or self.artists,
            album=other.album or self.album,
            genre=other.genre or self.genre,
            duration=other.duration or self.duration,
            bitrate=other.bitrate or self.bitrate,
            source_format=other.source_format or self.source_format,
            source_id=other.source_id or self.source_id,
            cover_data=other.cover_data or self.cover_data,
            cover_mime=other.cover_mime or self.cover_mime,
            embedded_lyrics=other.embedded_lyrics or self.embedded_lyrics,
            translated_lyrics=other.translated_lyrics or self.translated_lyrics,
            raw_metadata={**self.raw_metadata, **other.raw_metadata},
        )


@dataclass(slots=True)
class LyricsCandidate:
    """One potential lyric match returned by an online provider."""

    provider: str
    provider_id: str
    track_name: str
    artist_name: str
    album_name: str
    duration: float
    synced_lyrics: str = ""
    plain_lyrics: str = ""
    instrumental: bool = False
    confidence: float = 0.0


@dataclass(slots=True)
class LyricsResolution:
    """Result of resolving lyrics for a track."""

    status: LyricsStatus
    provider: str = ""
    content: str = ""
    synced: bool = False
    confidence: float = 0.0
    message: str = ""
    candidates: list[LyricsCandidate] = field(default_factory=list)


@dataclass(slots=True)
class ConversionOptions:
    """User-selected batch conversion settings."""

    output_dir: Path
    output_format: str = "mp3"
    bitrate_kbps: int = 320
    rename: bool = True
    name_template: str = "{artist} - {title}"
    group_by: tuple[str, ...] = ()
    fetch_lyrics: bool = True
    allow_unsynced_lyrics: bool = False
    overwrite_policy: OverwritePolicy = OverwritePolicy.RENAME
    workers: int = 2
    copy_cover: bool = True

    def validate(self) -> None:
        """Validate and normalize option values in place."""
        if not self.output_format:
            raise ValueError("必须指定输出格式。")
        if self.output_format not in {
            "mp3",
            "flac",
            "wav",
            "m4a",
            "alac",
            "ogg",
            "opus",
            "wma",
            "aiff",
            "ape",
        }:
            raise ValueError(f"不支持的输出格式：{self.output_format}")
        if not 32 <= int(self.bitrate_kbps) <= 512:
            raise ValueError("比特率必须在 32 到 512 kbps 之间。")
        allowed_groups = {"artist", "genre", "album"}
        unknown_groups = set(self.group_by) - allowed_groups
        if unknown_groups:
            raise ValueError(f"未知分类字段：{', '.join(sorted(unknown_groups))}")
        if not self.name_template.strip():
            raise ValueError("命名模板不能为空。")
        self.workers = max(1, min(int(self.workers), 8))


@dataclass(slots=True)
class ConversionResult:
    """Result for one source file."""

    source: Path
    status: JobStatus
    output_path: Path | None = None
    lrc_path: Path | None = None
    metadata: TrackMetadata | None = None
    lyrics: LyricsResolution | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

