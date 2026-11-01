"""Command-line interface used by users and cross-agent Skills."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from music_converter import __version__
from music_converter.lyrics import LyricsCache
from music_converter.media.ffmpeg import FORMAT_LABELS, OUTPUT_EXTENSIONS, FFmpeg
from music_converter.models import (
    ConversionOptions,
    ConversionResult,
    JobStatus,
    OverwritePolicy,
)
from music_converter.pipeline import ConversionEngine, collect_audio_files


def _json_print(payload: dict[str, Any]) -> None:
    """Print one UTF-8 JSON object on a single line."""
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def _result_payload(result: ConversionResult) -> dict[str, Any]:
    """Serialize a conversion result for CLI or Skill consumption."""
    return {
        "source": str(result.source),
        "status": result.status.value,
        "output": str(result.output_path) if result.output_path else None,
        "lrc": str(result.lrc_path) if result.lrc_path else None,
        "lyrics_status": result.lyrics.status.value if result.lyrics else None,
        "lyrics_provider": result.lyrics.provider if result.lyrics else None,
        "message": result.message,
        "warnings": result.warnings,
        "elapsed_seconds": result.elapsed_seconds,
    }


def _doctor(args: argparse.Namespace) -> int:
    """Print executable and encoder readiness."""
    ffmpeg = FFmpeg()
    payload = {
        "app": "MusicFormatConverter",
        "version": __version__,
        "python": sys.version,
        "tools": ffmpeg.doctor(),
        "lyrics_cache": str(LyricsCache().path),
    }
    if args.json:
        _json_print(payload)
    else:
        print(f"MusicFormatConverter {__version__}")
        print(f"FFmpeg: {payload['tools']['ffmpeg'] or '未找到'}")
        print(f"FFprobe: {payload['tools']['ffprobe'] or '未找到'}")
        print(f"Monkey's Audio: {payload['tools']['monkeys_audio'] or '未找到'}")
        for name, ready in payload["tools"].get("formats", {}).items():
            print(f"{FORMAT_LABELS.get(name, name)}: {'可用' if ready else '不可用'}")
    return 0 if payload["tools"]["ffmpeg_ready"] else 2


def _parse_group_by(raw: list[str]) -> tuple[str, ...]:
    """Normalize comma-separated and repeated group options."""
    values: list[str] = []
    for item in raw:
        values.extend(part.strip() for part in item.split(",") if part.strip())
    return tuple(dict.fromkeys(values))


def _dry_run(args: argparse.Namespace, files: list[Path]) -> int:
    """Print the conversion plan without mutating the file system."""
    payload = {
        "event": "dry_run",
        "count": len(files),
        "inputs": [str(path) for path in files],
        "output_dir": str(Path(args.output).expanduser().resolve()),
        "format": args.format,
        "extension": OUTPUT_EXTENSIONS[args.format],
        "bitrate_kbps": (
            args.bitrate
            if args.format in {"mp3", "m4a", "ogg", "opus", "wma"}
            else None
        ),
        "name_template": "{title}" if args.no_rename else args.name_template,
        "group_by": list(_parse_group_by(args.group_by)),
        "lyrics": not args.no_lyrics,
    }
    if args.json:
        _json_print(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _convert(args: argparse.Namespace) -> int:
    """Run a batch conversion and print machine-readable or text results."""
    paths = [Path(item) for item in args.inputs]
    files = collect_audio_files(paths, recursive=not args.no_recursive)
    if not files:
        message = "未找到受支持的音频文件。"
        if args.json:
            _json_print({"event": "error", "message": message})
        else:
            print(message, file=sys.stderr)
        return 2
    if args.dry_run:
        return _dry_run(args, files)

    try:
        options = ConversionOptions(
            output_dir=Path(args.output).expanduser().resolve(),
            output_format=args.format,
            bitrate_kbps=args.bitrate,
            rename=not args.no_rename,
            name_template=args.name_template,
            group_by=_parse_group_by(args.group_by),
            fetch_lyrics=not args.no_lyrics,
            allow_unsynced_lyrics=args.allow_unsynced,
            overwrite_policy=OverwritePolicy(args.overwrite),
            workers=args.workers,
        )
        options.validate()
        engine = ConversionEngine(options)
    except ValueError as exc:
        if args.json:
            _json_print({"event": "error", "message": str(exc)})
        else:
            print(str(exc), file=sys.stderr)
        return 2

    results: list[ConversionResult] = []
    if args.workers == 1 or len(files) == 1:
        for path in files:
            result = engine.convert(path)
            results.append(result)
            if not args.json:
                _print_text_result(result)
    else:
        with ThreadPoolExecutor(max_workers=min(args.workers, len(files))) as executor:
            future_map = {executor.submit(engine.convert, path): path for path in files}
            for future in as_completed(future_map):
                result = future.result()
                results.append(result)
                if not args.json:
                    _print_text_result(result)
    results.sort(key=lambda item: files.index(item.source))

    successes = sum(item.status is JobStatus.SUCCESS for item in results)
    skipped = sum(item.status is JobStatus.SKIPPED for item in results)
    failed = sum(item.status is JobStatus.FAILED for item in results)
    cancelled = sum(item.status is JobStatus.CANCELLED for item in results)
    summary = {
        "event": "summary",
        "total": len(results),
        "success": successes,
        "skipped": skipped,
        "failed": failed,
        "cancelled": cancelled,
        "results": [_result_payload(result) for result in results],
    }
    if args.json:
        _json_print(summary)
    else:
        print(f"\n完成：{successes}，跳过：{skipped}，失败：{failed}，取消：{cancelled}")
    if failed:
        return 1
    if cancelled:
        return 130
    return 0


def _print_text_result(result: ConversionResult) -> None:
    """Print one concise human-readable result."""
    marker = {
        JobStatus.SUCCESS: "完成",
        JobStatus.SKIPPED: "跳过",
        JobStatus.FAILED: "失败",
        JobStatus.CANCELLED: "取消",
        JobStatus.PENDING: "等待",
        JobStatus.RUNNING: "处理中",
    }[result.status]
    target = result.output_path or result.source
    print(f"[{marker}] {result.source.name} -> {target}")
    if result.message:
        print(f"  {result.message}")
    for warning in result.warnings:
        print(f"  警告：{warning}")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="music-converter",
        description="批量转换音乐、NCM，并匹配歌词。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="检查 FFmpeg、FFprobe、APE 编码器和格式支持")
    doctor.add_argument("--json", action="store_true", help="输出 JSON")
    doctor.set_defaults(func=_doctor)

    convert = subparsers.add_parser("convert", help="批量转换音频或 NCM")
    convert.add_argument("inputs", nargs="+", help="源文件或目录")
    convert.add_argument("-o", "--output", required=True, help="输出根目录")
    convert.add_argument(
        "-f",
        "--format",
        choices=sorted(OUTPUT_EXTENSIONS),
        default="mp3",
        help="目标格式，默认 mp3",
    )
    convert.add_argument("-b", "--bitrate", type=int, default=320, help="有损格式比特率，默认 320")
    convert.add_argument(
        "--name-template",
        default="{artist} - {title}",
        help="命名模板，可用 {artist} {title} {album} {genre}",
    )
    convert.add_argument("--no-rename", action="store_true", help="只使用歌曲名")
    convert.add_argument(
        "--group-by",
        action="append",
        default=[],
        metavar="FIELD",
        help="按 artist、genre、album 分类，可重复或逗号分隔",
    )
    convert.add_argument("--no-lyrics", action="store_true", help="关闭歌词匹配")
    convert.add_argument("--allow-unsynced", action="store_true", help="允许无时间轴歌词")
    convert.add_argument(
        "--overwrite",
        choices=[item.value for item in OverwritePolicy],
        default=OverwritePolicy.RENAME.value,
        help="同名文件处理方式，默认 rename",
    )
    convert.add_argument("-j", "--workers", type=int, default=2, help="并发文件数，默认 2")
    convert.add_argument("--no-recursive", action="store_true", help="目录只扫描第一层")
    convert.add_argument("--dry-run", action="store_true", help="只输出计划，不转换")
    convert.add_argument("--json", action="store_true", help="输出 JSON Lines")
    convert.set_defaults(func=_convert)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

