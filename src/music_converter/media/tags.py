"""Read and write common audio metadata using Mutagen."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.asf import ASF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TCON, TIT2, TPE1, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from PIL import Image

from music_converter.media.ffmpeg import MediaInfo
from music_converter.models import TrackMetadata


class MetadataError(RuntimeError):
    """Raised when media metadata cannot be read or written."""


def _first_value(tags: Any, names: tuple[str, ...]) -> str:
    """Return the first non-empty scalar value for candidate tag names."""
    if tags is None:
        return ""
    for name in names:
        try:
            value = tags.get(name)
        except (KeyError, TypeError, ValueError):
            continue
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if hasattr(value, "text"):
            value = value.text
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
        text = str(value).strip()
        if text:
            return text
    return ""


def _cover_mime(data: bytes) -> str:
    """Detect a cover image MIME type using Pillow."""
    try:
        with Image.open(BytesIO(data)) as image:
            fmt = (image.format or "").lower()
    except Exception:
        return ""
    return {
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "bmp": "image/bmp",
    }.get(fmt, f"image/{fmt}" if fmt else "")


def _extract_cover(audio: Any) -> tuple[bytes | None, str]:
    """Extract the first front-cover image from common container types."""
    if isinstance(audio, MP3) and audio.tags:
        pictures = audio.tags.getall("APIC")
        if pictures:
            picture = next(
                (item for item in pictures if item.type == 3),
                pictures[0],
            )
            return bytes(picture.data), picture.mime or _cover_mime(bytes(picture.data))
    if isinstance(audio, FLAC) and audio.pictures:
        picture = next(
            (item for item in audio.pictures if item.type == 3),
            audio.pictures[0],
        )
        return bytes(picture.data), picture.mime or _cover_mime(bytes(picture.data))
    if isinstance(audio, MP4) and audio.tags and audio.tags.get("covr"):
        cover = audio.tags["covr"][0]
        data = bytes(cover)
        is_png = getattr(cover, "imageformat", None) == MP4Cover.FORMAT_PNG
        mime = "image/png" if is_png else "image/jpeg"
        return data, mime
    if isinstance(audio, (WAVE, AIFF)) and audio.tags:
        pictures = audio.tags.getall("APIC") if hasattr(audio.tags, "getall") else []
        if pictures:
            picture = pictures[0]
            return bytes(picture.data), picture.mime or _cover_mime(bytes(picture.data))
    if isinstance(audio, ASF) and audio.tags:
        for key in ("WM/Picture", "Picture"):
            if key in audio.tags:
                value = audio.tags[key][0]
                raw = bytes(value.value)
                if b"\x00" in raw:
                    raw = raw.split(b"\x00", 1)[1]
                return raw, _cover_mime(raw)
    return None, ""


def _extract_embedded_lyrics(audio: Any) -> str:
    """Extract unsynchronized or LRC-like lyrics already stored in the file."""
    if isinstance(audio, MP3) and audio.tags:
        for frame in audio.tags.getall("USLT"):
            text = str(frame.text or "").strip()
            if text:
                return text
    if isinstance(audio, MP4) and audio.tags:
        values = audio.tags.get("\xa9lyr") or []
        if values:
            return str(values[0]).strip()
    if isinstance(audio, (FLAC, OggVorbis, OggOpus)) and audio.tags:
        for key in ("lyrics", "unsyncedlyrics", "lyric", "lrc"):
            values = audio.tags.get(key) or []
            if values:
                return str(values[0]).strip()
    if isinstance(audio, ASF) and audio.tags:
        for key in ("WM/Lyrics", "Lyrics"):
            if key in audio.tags:
                return str(audio.tags[key][0]).strip()
    return ""


def _filename_metadata(path: Path) -> tuple[list[str], str]:
    """Infer artist and title from a conventional ``Artist - Title`` filename."""
    stem = path.stem.strip()
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return ([artist.strip()] if artist.strip() else []), title.strip()
    return [], stem


def read_metadata(path: str | Path, media_info: MediaInfo) -> TrackMetadata:
    """Read normalized tags and artwork from an audio file."""
    source = Path(path)
    fallback_artists, fallback_title = _filename_metadata(source)
    try:
        easy = MutagenFile(source, easy=True)
        full = MutagenFile(source)
    except Exception:
        easy = None
        full = None

    title = _first_value(easy.tags if easy else None, ("title", "©nam")) or fallback_title
    artist_value = _first_value(
        easy.tags if easy else None,
        ("artist", "albumartist", "©ART", "aART"),
    )
    artists = (
        [part.strip() for part in artist_value.replace(";", "/").split("/") if part.strip()]
        if artist_value
        else fallback_artists
    )
    album = _first_value(
        easy.tags if easy else None,
        ("album", "©alb", "WM/AlbumTitle"),
    )
    genre = _first_value(
        easy.tags if easy else None,
        ("genre", "©gen", "WM/Genre"),
    )
    cover_data, cover_mime = _extract_cover(full)
    embedded_lyrics = _extract_embedded_lyrics(full)
    return TrackMetadata(
        title=title,
        artists=artists,
        album=album,
        genre=genre,
        duration=media_info.duration,
        bitrate=media_info.bitrate,
        source_format=media_info.codec_name or source.suffix.lstrip("."),
        cover_data=cover_data,
        cover_mime=cover_mime,
        embedded_lyrics=embedded_lyrics,
    )


def _set_id3_tags(audio: Any, metadata: TrackMetadata, include_cover: bool) -> None:
    """Set common ID3 frames on MP3, WAV, or AIFF objects."""
    if audio.tags is None:
        audio.add_tags()
    tags: ID3 = audio.tags
    for frame_id in ("TIT2", "TALB", "TPE1", "TPE2", "TCON", "APIC"):
        tags.delall(frame_id)
    if metadata.title:
        tags.add(TIT2(encoding=3, text=[metadata.title]))
    if metadata.artist_text:
        tags.add(TPE1(encoding=3, text=[metadata.artist_text]))
        tags.add(TPE2(encoding=3, text=[metadata.artist_text]))
    if metadata.album:
        tags.add(TALB(encoding=3, text=[metadata.album]))
    if metadata.genre:
        tags.add(TCON(encoding=3, text=[metadata.genre]))
    if include_cover and metadata.cover_data:
        tags.add(
            APIC(
                encoding=3,
                mime=metadata.cover_mime or _cover_mime(metadata.cover_data) or "image/jpeg",
                type=3,
                desc="Cover",
                data=metadata.cover_data,
            )
        )
    audio.save(v2_version=3)


def _picture_from_cover(metadata: TrackMetadata) -> Picture | None:
    """Build a FLAC picture block with dimensions when the image is readable."""
    if not metadata.cover_data:
        return None
    picture = Picture()
    picture.type = 3
    picture.data = metadata.cover_data
    picture.mime = metadata.cover_mime or _cover_mime(metadata.cover_data) or "image/jpeg"
    picture.desc = "Cover"
    try:
        with Image.open(BytesIO(metadata.cover_data)) as image:
            picture.width = image.width
            picture.height = image.height
            picture.depth = len(image.getbands()) * 8
    except Exception:
        picture.width = 0
        picture.height = 0
        picture.depth = 0
    return picture


def write_metadata(
    path: str | Path,
    metadata: TrackMetadata,
    output_format: str,
    *,
    include_cover: bool = True,
) -> list[str]:
    """Write normalized metadata and artwork into the converted audio file.

    Returns:
        Non-fatal warnings generated during tag writing.
    """
    target = Path(path)
    warnings: list[str] = []
    try:
        if output_format == "mp3":
            _set_id3_tags(MP3(target, ID3=ID3), metadata, include_cover)
        elif output_format == "flac":
            audio = FLAC(target)
            audio["title"] = [metadata.title] if metadata.title else []
            audio["artist"] = metadata.artists
            audio["albumartist"] = [metadata.artist_text] if metadata.artist_text else []
            audio["album"] = [metadata.album] if metadata.album else []
            audio["genre"] = [metadata.genre] if metadata.genre else []
            audio.clear_pictures()
            if include_cover:
                picture = _picture_from_cover(metadata)
                if picture:
                    audio.add_picture(picture)
            audio.save()
        elif output_format in {"wav", "aiff"}:
            audio = WAVE(target, ID3=ID3) if output_format == "wav" else AIFF(target, ID3=ID3)
            _set_id3_tags(audio, metadata, include_cover)
        elif output_format in {"ogg", "opus"}:
            audio = OggVorbis(target) if output_format == "ogg" else OggOpus(target)
            audio["title"] = [metadata.title] if metadata.title else []
            audio["artist"] = metadata.artists
            audio["album"] = [metadata.album] if metadata.album else []
            audio["genre"] = [metadata.genre] if metadata.genre else []
            if include_cover and metadata.cover_data:
                picture = _picture_from_cover(metadata)
                if picture:
                    audio["metadata_block_picture"] = [
                        base64.b64encode(picture.write()).decode("ascii")
                    ]
            audio.save()
        elif output_format in {"m4a", "alac"}:
            audio = MP4(target)
            if audio.tags is None:
                audio.add_tags()
            if metadata.title:
                audio.tags["\xa9nam"] = [metadata.title]
            if metadata.artist_text:
                audio.tags["\xa9ART"] = [metadata.artist_text]
                audio.tags["aART"] = [metadata.artist_text]
            if metadata.album:
                audio.tags["\xa9alb"] = [metadata.album]
            if metadata.genre:
                audio.tags["\xa9gen"] = [metadata.genre]
            if include_cover and metadata.cover_data:
                fmt = (
                    MP4Cover.FORMAT_PNG
                    if (metadata.cover_mime or _cover_mime(metadata.cover_data)).endswith("png")
                    else MP4Cover.FORMAT_JPEG
                )
                audio.tags["covr"] = [MP4Cover(metadata.cover_data, imageformat=fmt)]
            audio.save()
        elif output_format == "wma":
            audio = ASF(target)
            audio["Title"] = [metadata.title] if metadata.title else []
            audio["Author"] = [metadata.artist_text] if metadata.artist_text else []
            audio["WM/AlbumTitle"] = [metadata.album] if metadata.album else []
            audio["WM/Genre"] = [metadata.genre] if metadata.genre else []
            audio.save()
            if include_cover and metadata.cover_data:
                warnings.append("WMA 封面写入未实现，音频文件已成功生成。")
        elif output_format == "ape":
            from mutagen.monkeysaudio import MonkeysAudio

            audio = MonkeysAudio(target)
            if audio.tags is None:
                audio.add_tags()
            audio["Title"] = metadata.title
            audio["Artist"] = metadata.artist_text
            audio["Album"] = metadata.album
            audio["Genre"] = metadata.genre
            if include_cover and metadata.cover_data:
                audio["Cover Art (Front)"] = (
                    b"cover.jpg\x00" + metadata.cover_data
                )
            audio.save()
        else:
            warnings.append(f"格式 {output_format} 未配置标签写入。")
    except Exception as exc:
        warnings.append(f"音频标签写入失败：{exc}")
    return warnings

