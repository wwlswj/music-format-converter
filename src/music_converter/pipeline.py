"""End-to-end conversion pipeline for ordinary audio and NCM files."""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from music_converter.lyrics import LyricsResolver
from music_converter.media.ffmpeg import (
    LOSSY_FORMATS,
    OUTPUT_EXTENSIONS,
    FFmpeg,
    MonkeysAudio,
    ToolError,
)
from music_converter.media.ncm import (
    NcmError,
    decrypt_ncm_audio,
    parse_ncm,
)
from music_converter.media.tags import read_metadata, write_metadata
from music_converter.models import (
    ConversionOptions,
    ConversionResult,
    JobStatus,
    LyricsResolution,
    LyricsStatus,
    TrackMetadata,
)
from music_converter.naming import (
    build_output_directory,
    build_output_stem,
    resolve_destination,
)

ProgressCallback = Callable[[float], None]


def _safe_progress(callback: ProgressCallback | None, value: float) -> None:
    """Clamp and dispatch a progress value."""
    if callback:
        callback(max(0.0, min(float(value), 1.0)))


def _ensure_source(path: Path) -> Path:
    """Validate that a source path is an existing file."""
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"源文件不存在：{source}")
    supported = {
        ".ncm",
        ".mp3",
        ".flac",
        ".wav",
        ".ape",
        ".m4a",
        ".aac",
        ".ogg",
        ".opus",
        ".wma",
        ".aiff",
        ".aif",
        ".alac",
    }
    if source.suffix.casefold() not in supported:
        raise ValueError(f"暂不支持的源文件扩展名：{source.suffix}")
    return source


class ConversionEngine:
    """Run one complete conversion through a shared, reusable pipeline."""

    def __init__(
        self,
        options: ConversionOptions,
        *,
        ffmpeg: FFmpeg | None = None,
        monkeys_audio: MonkeysAudio | None = None,
        lyrics_resolver: LyricsResolver | None = None,
    ) -> None:
        """Create a conversion engine bound to the requested options."""
        options.validate()
        self.options = options
        self.ffmpeg = ffmpeg or FFmpeg()
        self.monkeys_audio = monkeys_audio or MonkeysAudio(self.ffmpeg.tools)
        self.lyrics_resolver = lyrics_resolver or LyricsResolver()

    def convert(
        self,
        source_path: str | Path,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ConversionResult:
        """Convert one source and always return a structured result."""
        started = time.monotonic()
        source = Path(source_path)
        try:
            source = _ensure_source(source)
            result = self._convert_impl(
                source,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
        except InterruptedError:
            result = ConversionResult(
                source=source,
                status=JobStatus.CANCELLED,
                message="转换任务已取消。",
            )
        except Exception as exc:
            result = ConversionResult(
                source=source,
                status=JobStatus.FAILED,
                message=str(exc) or exc.__class__.__name__,
            )
        result.elapsed_seconds = round(time.monotonic() - started, 3)
        return result

    def _convert_impl(
        self,
        source: Path,
        *,
        progress_callback: ProgressCallback | None,
        cancel_event: threading.Event | None,
    ) -> ConversionResult:
        """Perform the actual conversion inside an isolated temporary directory."""
        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []

        with tempfile.TemporaryDirectory(prefix=".mfc-", dir=self.options.output_dir) as temp_raw:
            temp_dir = Path(temp_raw)
            if cancel_event and cancel_event.is_set():
                raise InterruptedError

            metadata, working_audio = self._load_source(source, temp_dir)
            _safe_progress(progress_callback, 0.12)

            if cancel_event and cancel_event.is_set():
                raise InterruptedError
            lyrics = self._resolve_lyrics(source, metadata)
            _safe_progress(progress_callback, 0.2)

            destination_dir = build_output_directory(
                self.options.output_dir,
                metadata,
                self.options.group_by,
            )
            destination_dir.mkdir(parents=True, exist_ok=True)
            stem = build_output_stem(metadata, self.options)
            extension = OUTPUT_EXTENSIONS[self.options.output_format]
            destination, should_skip = resolve_destination(
                destination_dir,
                stem,
                extension,
                self.options.overwrite_policy,
            )
            if should_skip:
                return ConversionResult(
                    source=source,
                    status=JobStatus.SKIPPED,
                    output_path=destination,
                    metadata=metadata,
                    lyrics=lyrics,
                    message="目标文件已存在，按设置跳过。",
                )

            temporary_output = temp_dir / f"converted.{extension}"
            if cancel_event and cancel_event.is_set():
                raise InterruptedError

            if self.options.output_format == "ape":
                wav_path = temp_dir / "intermediate.wav"
                self.ffmpeg.convert(
                    working_audio,
                    wav_path,
                    "wav",
                    self.options.bitrate_kbps,
                    metadata.duration,
                    progress_callback=lambda value: _safe_progress(
                        progress_callback,
                        0.2 + value * 0.65,
                    ),
                    cancel_event=cancel_event,
                )
                _safe_progress(progress_callback, 0.88)
                self.monkeys_audio.encode(wav_path, temporary_output, metadata)
            else:
                bitrate = (
                    self.options.bitrate_kbps
                    if self.options.output_format in LOSSY_FORMATS
                    else 0
                )
                self.ffmpeg.convert(
                    working_audio,
                    temporary_output,
                    self.options.output_format,
                    bitrate,
                    metadata.duration,
                    progress_callback=lambda value: _safe_progress(
                        progress_callback,
                        0.2 + value * 0.68,
                    ),
                    cancel_event=cancel_event,
                )

            _safe_progress(progress_callback, 0.9)
            warnings.extend(
                write_metadata(
                    temporary_output,
                    metadata,
                    self.options.output_format,
                    include_cover=self.options.copy_cover,
                )
            )
            self._verify_output(temporary_output, metadata.duration)
            _safe_progress(progress_callback, 0.96)

            temporary_output.replace(destination)
            try:
                lrc_path = self._write_lrc(destination, lyrics)
            except OSError as exc:
                lrc_path = None
                warnings.append(f"LRC 歌词写入失败：{exc}")
            _safe_progress(progress_callback, 1.0)
            return ConversionResult(
                source=source,
                status=JobStatus.SUCCESS,
                output_path=destination,
                lrc_path=lrc_path,
                metadata=metadata,
                lyrics=lyrics,
                warnings=warnings,
            )

    def _load_source(self, source: Path, temp_dir: Path) -> tuple[TrackMetadata, Path]:
        """Load metadata and return the audio stream path to transcode."""
        if source.suffix.casefold() == ".ncm":
            container = parse_ncm(source)
            decrypted = temp_dir / f"decrypted.{container.original_extension}"
            decrypt_ncm_audio(container, decrypted)
            try:
                info = self.ffmpeg.probe(decrypted)
            except ToolError as exc:
                raise NcmError(
                    "NCM 解密完成，但底层音频无法播放；已阻止生成损坏文件。"
                ) from exc
            file_metadata = read_metadata(decrypted, info)
            metadata = file_metadata.merged_with(container.metadata)
            if metadata.title in {"", decrypted.stem} or not metadata.artists:
                stem = source.stem.strip()
                filename_artist = ""
                filename_title = stem
                if " - " in stem:
                    filename_artist, filename_title = stem.split(" - ", 1)
                if not metadata.title:
                    metadata.title = filename_title.strip()
                if not metadata.artists and filename_artist.strip():
                    metadata.artists = [filename_artist.strip()]
            metadata.duration = metadata.duration or info.duration
            metadata.source_format = info.codec_name or container.original_extension
            return metadata, decrypted

        info = self.ffmpeg.probe(source)
        metadata = read_metadata(source, info)
        metadata.duration = metadata.duration or info.duration
        return metadata, source

    def _resolve_lyrics(self, source: Path, metadata: TrackMetadata) -> LyricsResolution:
        """Resolve lyrics while preserving a usable result on provider failures."""
        return self.lyrics_resolver.resolve(
            source,
            metadata,
            fetch_online=self.options.fetch_lyrics,
            allow_unsynced=self.options.allow_unsynced_lyrics,
        )

    def _verify_output(self, output: Path, expected_duration: float) -> None:
        """Ensure the generated file is a readable audio stream with plausible duration."""
        info = self.ffmpeg.probe(output)
        if info.duration <= 0:
            raise ToolError("输出文件时长无效。")
        if expected_duration > 0:
            tolerance = max(2.0, expected_duration * 0.01)
            if abs(info.duration - expected_duration) > tolerance:
                raise ToolError(
                    f"输出时长异常：源 {expected_duration:.1f}s，输出 {info.duration:.1f}s。"
                )

    @staticmethod
    def _write_lrc(
        audio_path: Path,
        lyrics: LyricsResolution,
    ) -> Path | None:
        """Write a sidecar UTF-8 LRC when a usable resolution exists."""
        if not lyrics.content or lyrics.status in {
            LyricsStatus.NOT_REQUESTED,
            LyricsStatus.INSTRUMENTAL,
            LyricsStatus.PENDING,
            LyricsStatus.NOT_FOUND,
            LyricsStatus.ERROR,
        }:
            return None
        lrc_path = audio_path.with_suffix(".lrc")
        temp_path = lrc_path.with_name(f".{lrc_path.name}.part")
        try:
            temp_path.write_text(lyrics.content, encoding="utf-8", newline="\n")
            temp_path.replace(lrc_path)
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise
        return lrc_path


def collect_audio_files(paths: list[str | Path], recursive: bool = True) -> list[Path]:
    """Expand files and directories into a stable, de-duplicated source list."""
    supported = {
        ".ncm",
        ".mp3",
        ".flac",
        ".wav",
        ".ape",
        ".m4a",
        ".aac",
        ".ogg",
        ".opus",
        ".wma",
        ".aiff",
        ".aif",
        ".alac",
    }
    found: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if path.is_file() and path.suffix.casefold() in supported:
            found.append(path.resolve())
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.iterdir()
            for item in iterator:
                if item.is_file() and item.suffix.casefold() in supported:
                    found.append(item.resolve())
    return list(dict.fromkeys(found))


def move_to_trash_safely(path: Path) -> None:
    """Move a generated temporary file into a local trash directory.

    This helper is intentionally limited to files under the application data
    directory or its caller-selected output tree.
    """
    target = path.resolve()
    trash = target.parent / ".mfc-trash"
    trash.mkdir(exist_ok=True)
    destination = trash / target.name
    if destination.exists():
        destination = trash / f"{target.stem}-{int(time.time())}{target.suffix}"
    shutil.move(str(target), str(destination))

