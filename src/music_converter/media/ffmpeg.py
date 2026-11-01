"""FFmpeg discovery, probing, conversion, and capability checks."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from music_converter.config import application_root
from music_converter.models import TrackMetadata

ProgressCallback = Callable[[float], None]

OUTPUT_EXTENSIONS = {
    "mp3": "mp3",
    "flac": "flac",
    "wav": "wav",
    "m4a": "m4a",
    "alac": "m4a",
    "ogg": "ogg",
    "opus": "opus",
    "wma": "wma",
    "aiff": "aiff",
    "ape": "ape",
}

FORMAT_LABELS = {
    "mp3": "MP3",
    "flac": "FLAC",
    "wav": "WAV",
    "m4a": "M4A (AAC)",
    "alac": "ALAC (M4A)",
    "ogg": "OGG Vorbis",
    "opus": "Opus",
    "wma": "WMA",
    "aiff": "AIFF",
    "ape": "APE",
}

LOSSY_FORMATS = {"mp3", "m4a", "ogg", "opus", "wma"}
LOSSLESS_FORMATS = {"flac", "wav", "alac", "aiff", "ape"}

_ENCODERS: dict[str, tuple[str, list[str]]] = {
    "mp3": ("libmp3lame", ["-f", "mp3"]),
    "flac": ("flac", ["-f", "flac", "-compression_level", "6"]),
    "wav": ("pcm_s24le", ["-f", "wav"]),
    "m4a": ("aac", ["-f", "ipod", "-movflags", "+faststart"]),
    "alac": ("alac", ["-f", "ipod", "-movflags", "+faststart"]),
    "ogg": ("libvorbis", ["-f", "ogg"]),
    "opus": ("libopus", ["-f", "opus"]),
    "wma": ("wmav2", ["-f", "asf"]),
    "aiff": ("pcm_s24be", ["-f", "aiff"]),
}


class ToolError(RuntimeError):
    """Raised when an external media tool is missing or fails."""


@dataclass(slots=True)
class MediaInfo:
    """Relevant audio properties reported by FFprobe."""

    path: Path
    duration: float
    format_name: str
    codec_name: str
    sample_rate: int
    channels: int
    bitrate: int


@dataclass(slots=True)
class ToolPaths:
    """Resolved external executable paths."""

    ffmpeg: Path | None
    ffprobe: Path | None
    mac: Path | None

    @classmethod
    def discover(cls, explicit_root: str | Path | None = None) -> ToolPaths:
        """Find tools in the project, environment variables, or PATH."""
        project_root = application_root()
        root = Path(explicit_root).resolve() if explicit_root else project_root
        ffmpeg_candidates = [
            root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
            root / "tools" / "ffmpeg" / "ffmpeg.exe",
            Path(os.environ.get("FFMPEG_PATH", "")),
        ]
        ffprobe_candidates = [
            root / "tools" / "ffmpeg" / "bin" / "ffprobe.exe",
            root / "tools" / "ffmpeg" / "ffprobe.exe",
            Path(os.environ.get("FFPROBE_PATH", "")),
        ]
        mac_candidates = [
            root / "tools" / "monkeys-audio" / "MAC.exe",
            root / "tools" / "monkeys-audio" / "mac.exe",
            Path(os.environ.get("MAC_PATH", "")),
        ]

        ffmpeg = _first_existing(ffmpeg_candidates) or _which("ffmpeg")
        ffprobe = _first_existing(ffprobe_candidates) or _which("ffprobe")
        mac = _first_existing(mac_candidates) or _which("mac")
        return cls(ffmpeg=ffmpeg, ffprobe=ffprobe, mac=mac)


def _first_existing(candidates: list[Path]) -> Path | None:
    """Return the first existing file, ignoring empty environment entries."""
    for candidate in candidates:
        if candidate and str(candidate) and candidate.is_file():
            return candidate
    return None


def _which(name: str) -> Path | None:
    """Return a command path or ``None``."""
    found = shutil.which(name)
    return Path(found) if found else None


def _no_window_kwargs() -> dict:
    """Return subprocess flags that avoid flashing console windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


class FFmpeg:
    """Small subprocess adapter around FFmpeg and FFprobe."""

    def __init__(self, tools: ToolPaths | None = None) -> None:
        """Store the executable paths."""
        self.tools = tools or ToolPaths.discover()

    def require_ffmpeg(self) -> Path:
        """Return FFmpeg or raise a useful error."""
        if not self.tools.ffmpeg or not self.tools.ffmpeg.is_file():
            raise ToolError("未找到 FFmpeg。请重新运行 setup.ps1。")
        return self.tools.ffmpeg

    def require_ffprobe(self) -> Path:
        """Return FFprobe or raise a useful error."""
        if not self.tools.ffprobe or not self.tools.ffprobe.is_file():
            raise ToolError("未找到 FFprobe。请重新运行 setup.ps1。")
        return self.tools.ffprobe

    def probe(self, path: str | Path) -> MediaInfo:
        """Read media properties through FFprobe."""
        source = Path(path)
        command = [
            str(self.require_ffprobe()),
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name,bit_rate:stream=codec_type,codec_name,"
            "sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(source),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
                **_no_window_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(f"FFprobe 执行失败：{source}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            raise ToolError(detail[-1] if detail else f"无法识别媒体：{source}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ToolError("FFprobe 返回了无效 JSON。") from exc

        audio_stream = next(
            (item for item in payload.get("streams", []) if item.get("codec_type") == "audio"),
            None,
        )
        if not audio_stream:
            raise ToolError(f"文件中没有音频流：{source}")
        format_info = payload.get("format", {})

        def _integer(value: object) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        try:
            duration = float(format_info.get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        return MediaInfo(
            path=source,
            duration=duration,
            format_name=str(format_info.get("format_name") or ""),
            codec_name=str(audio_stream.get("codec_name") or ""),
            sample_rate=_integer(audio_stream.get("sample_rate")),
            channels=_integer(audio_stream.get("channels")),
            bitrate=_integer(audio_stream.get("bit_rate") or format_info.get("bit_rate")),
        )

    def available_encoders(self) -> set[str]:
        """Return encoder names reported by FFmpeg."""
        command = [str(self.require_ffmpeg()), "-hide_banner", "-encoders"]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
                **_no_window_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError("无法读取 FFmpeg 编码器列表。") from exc
        if result.returncode != 0:
            raise ToolError("无法读取 FFmpeg 编码器列表。")
        encoders: set[str] = set()
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and len(fields[0]) == 6:
                encoders.add(fields[1])
        return encoders

    def convert(
        self,
        source: str | Path,
        destination: str | Path,
        output_format: str,
        bitrate_kbps: int,
        duration: float,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Transcode one audio stream to the requested output format."""
        if output_format == "ape":
            raise ValueError("APE 输出必须由 MonkeysAudio 适配器完成。")
        if output_format not in _ENCODERS:
            raise ValueError(f"不支持的输出格式：{output_format}")
        encoder, output_args = _ENCODERS[output_format]
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)

        command = [
            str(self.require_ffmpeg()),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-c:a",
            encoder,
        ]
        if output_format == "ogg":
            requested = int(bitrate_kbps)
            if requested <= 128:
                quality = 4
            elif requested <= 160:
                quality = 5
            elif requested <= 192:
                quality = 6
            elif requested <= 224:
                quality = 7
            elif requested <= 256:
                quality = 8
            elif requested <= 320:
                quality = 9
            else:
                quality = 10
            command.extend(["-q:a", str(quality)])
        elif output_format in LOSSY_FORMATS:
            effective_bitrate = int(bitrate_kbps)
            if output_format == "opus" and effective_bitrate > 256:
                try:
                    source_info = self.probe(source)
                    if source_info.channels == 1:
                        effective_bitrate = 256
                except ToolError:
                    effective_bitrate = min(effective_bitrate, 256)
            command.extend(["-b:a", f"{effective_bitrate}k"])
        command.extend(output_args)
        command.extend(["-progress", "pipe:1", "-nostats", str(target)])

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **_no_window_kwargs(),
        )
        stdout_queue: queue.Queue[str | None] = queue.Queue()
        stderr_lines: list[str] = []

        def _read_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                stdout_queue.put(line)
            stdout_queue.put(None)

        def _read_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                stderr_lines.append(line.rstrip())
                if len(stderr_lines) > 200:
                    del stderr_lines[:100]

        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        cancelled = False
        try:
            while process.poll() is None:
                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    process.terminate()
                    break
                try:
                    line = stdout_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if line is None:
                    continue
                is_time_line = line.startswith(("out_time_us=", "out_time_ms="))
                if progress_callback and duration > 0 and is_time_line:
                    value = line.split("=", 1)[1].strip()
                    if value.isdigit():
                        progress_callback(min(0.99, int(value) / 1_000_000 / duration))
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        finally:
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)

        if cancelled:
            target.unlink(missing_ok=True)
            raise ToolError("转换任务已取消。")
        if process.returncode != 0:
            target.unlink(missing_ok=True)
            useful_lines = [line for line in stderr_lines if line.strip()]
            detail = "\n".join(useful_lines[-4:]) if useful_lines else "未知 FFmpeg 错误"
            raise ToolError(f"FFmpeg 转换失败：{detail}")
        if not target.is_file() or target.stat().st_size == 0:
            raise ToolError("FFmpeg 未生成有效输出文件。")
        if progress_callback:
            progress_callback(1.0)
        return target

    def doctor(self) -> dict:
        """Return machine-readable capability information."""
        result: dict = {
            "ffmpeg": str(self.tools.ffmpeg) if self.tools.ffmpeg else None,
            "ffprobe": str(self.tools.ffprobe) if self.tools.ffprobe else None,
            "monkeys_audio": str(self.tools.mac) if self.tools.mac else None,
            "ffmpeg_ready": bool(self.tools.ffmpeg and self.tools.ffprobe),
            "ape_output_ready": bool(self.tools.ffmpeg and self.tools.ffprobe and self.tools.mac),
            "formats": {},
        }
        if not result["ffmpeg_ready"]:
            return result
        try:
            encoders = self.available_encoders()
        except ToolError:
            return result
        for output_format, (encoder, _) in _ENCODERS.items():
            result["formats"][output_format] = encoder in encoders
        result["formats"]["ape"] = result["ape_output_ready"]
        return result


class MonkeysAudio:
    """Encode WAV input to APE using the official Monkey's Audio CLI."""

    def __init__(self, tools: ToolPaths | None = None) -> None:
        """Resolve the MAC executable."""
        self.tools = tools or ToolPaths.discover()

    @property
    def available(self) -> bool:
        """Return whether ``MAC.exe`` is available."""
        return bool(self.tools.mac and self.tools.mac.is_file())

    def encode(
        self,
        wav_path: Path,
        destination: Path,
        metadata: TrackMetadata,
        compression_level: int = 2000,
    ) -> Path:
        """Encode a WAV file to APE and add basic APEv2 tags."""
        if not self.tools.mac or not self.tools.mac.is_file():
            raise ToolError("未找到 Monkey's Audio MAC.exe，无法输出 APE。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        tag_parts = [
            f"Artist={metadata.artist_text}",
            f"Album={metadata.album}",
            f"Name={metadata.title}",
            f"Genre={metadata.genre}",
        ]
        command = [
            str(self.tools.mac),
            str(wav_path),
            str(destination),
            f"-c{int(compression_level)}",
            "-t",
            "|".join(tag_parts),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3600,
                check=False,
                **_no_window_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError("Monkey's Audio 编码失败。") from exc
        if result.returncode != 0 or not destination.is_file():
            detail = result.stderr.strip() or result.stdout.strip() or "未知错误"
            raise ToolError(f"Monkey's Audio 编码失败：{detail}")
        return destination

