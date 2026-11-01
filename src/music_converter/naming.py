"""Windows-safe naming, renaming, and directory organization."""

from __future__ import annotations

import re
from pathlib import Path

from music_converter.models import ConversionOptions, OverwritePolicy, TrackMetadata

_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_WHITESPACE = re.compile(r"\s+")
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_GROUP_ORDER = ("artist", "genre", "album")


def sanitize_component(value: str, *, fallback: str, max_length: int = 120) -> str:
    """Return a safe Windows file-system path component."""
    cleaned = _INVALID_WINDOWS_CHARS.sub("_", value or "")
    cleaned = _WHITESPACE.sub(" ", cleaned).strip(" .")
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned[:max_length].rstrip(" .") or fallback


def build_output_stem(metadata: TrackMetadata, options: ConversionOptions) -> str:
    """Build the output file stem from metadata and the user's template."""
    artist = sanitize_component(
        metadata.artist_text or "未知歌手",
        fallback="未知歌手",
        max_length=80,
    )
    title = sanitize_component(
        metadata.title or "未知歌曲",
        fallback="未知歌曲",
        max_length=100,
    )
    album = sanitize_component(metadata.album or "未知专辑", fallback="未知专辑")
    genre = sanitize_component(metadata.genre or "未知风格", fallback="未知风格")
    template = options.name_template if options.rename else "{title}"

    try:
        rendered = template.format(
            artist=artist,
            title=title,
            album=album,
            genre=genre,
        )
    except (KeyError, ValueError):
        rendered = f"{artist} - {title}"

    return sanitize_component(rendered, fallback=f"{artist} - {title}")


def build_output_directory(
    base_dir: Path,
    metadata: TrackMetadata,
    group_by: tuple[str, ...],
) -> Path:
    """Build category directories in the fixed order artist, genre, album."""
    selected = set(group_by)
    result = base_dir
    values = {
        "artist": sanitize_component(
            metadata.artist_text or "未知歌手",
            fallback="未知歌手",
            max_length=80,
        ),
        "genre": sanitize_component(
            metadata.genre or "未知风格",
            fallback="未知风格",
            max_length=80,
        ),
        "album": sanitize_component(
            metadata.album or "未知专辑",
            fallback="未知专辑",
            max_length=80,
        ),
    }
    for key in _GROUP_ORDER:
        if key in selected:
            result /= values[key]
    return result


def _numbered_path(path: Path, index: int) -> Path:
    """Return ``stem (n).suffix`` for the requested collision index."""
    return path.with_name(f"{path.stem} ({index}){path.suffix}")


def resolve_destination(
    base_dir: Path,
    stem: str,
    extension: str,
    policy: OverwritePolicy,
) -> tuple[Path, bool]:
    """Resolve a destination path according to the overwrite policy.

    Returns:
        A ``(path, should_skip)`` tuple.
    """
    destination = base_dir / f"{stem}.{extension.lstrip('.')}"

    def _has_collision(path: Path) -> bool:
        return path.exists() or path.with_suffix(".lrc").exists()

    if not _has_collision(destination):
        return destination, False
    if policy is OverwritePolicy.REPLACE:
        return destination, False
    if policy is OverwritePolicy.SKIP:
        return destination, True

    index = 2
    while True:
        candidate = _numbered_path(destination, index)
        if not _has_collision(candidate):
            return candidate, False
        index += 1

