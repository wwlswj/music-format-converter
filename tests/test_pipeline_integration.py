"""Integration tests using generated, copyright-free audio fixtures."""

from __future__ import annotations

import base64
import json
import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from PIL import Image

from music_converter.media.ffmpeg import OUTPUT_EXTENSIONS, FFmpeg, ToolPaths
from music_converter.media.ncm import (
    _AES_KEY_METADATA,
    _AES_KEY_RC4,
    _METADATA_PREFIX,
    _METADATA_XOR,
    _RC4_XOR,
    NCM_MAGIC,
)
from music_converter.media.tags import read_metadata
from music_converter.models import ConversionOptions, JobStatus, OverwritePolicy
from music_converter.pipeline import ConversionEngine


@pytest.fixture()
def tools() -> ToolPaths:
    """Return local media tools or skip if they are unavailable."""
    paths = ToolPaths.discover()
    if not paths.ffmpeg or not paths.ffprobe:
        pytest.skip("FFmpeg tools are not installed")
    return paths


def _make_wave(tools: ToolPaths, destination: Path) -> None:
    """Generate a short sine-wave WAV fixture."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(tools.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.5",
            "-c:a",
            "pcm_s16le",
            str(destination),
            "-y",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _aes_encrypt(key: bytes, data: bytes) -> bytes:
    """Encrypt padded fixture data with AES-ECB."""
    return AES.new(key, AES.MODE_ECB).encrypt(pad(data, 16))


def _reference_ncm_xor(data: bytes, key: bytes) -> bytes:
    """Independently implement the NCM RC4 variant used by the C++ reference."""
    state = list(range(256))
    last_byte = 0
    key_offset = 0
    for index in range(256):
        current = state[index]
        swap_index = (current + last_byte + key[key_offset]) & 0xFF
        key_offset = (key_offset + 1) % len(key)
        state[index] = state[swap_index]
        state[swap_index] = current
        last_byte = swap_index
    mask = bytes(
        state[
            (
                state[(index + 1) & 0xFF]
                + state[(state[(index + 1) & 0xFF] + index + 1) & 0xFF]
            )
            & 0xFF
        ]
        for index in range(256)
    )
    repeated = (mask * ((len(data) + 255) // 256))[: len(data)]
    return bytes(left ^ right for left, right in zip(data, repeated, strict=True))


def _wrap_ncm(
    destination: Path,
    *,
    audio_bytes: bytes,
    metadata: dict,
    cover: bytes,
) -> None:
    """Create a synthetic NCM container from an MP3 byte stream."""
    rc4_key = bytes.fromhex("00112233445566778899aabbccddeeff")
    encrypted_key = _aes_encrypt(_AES_KEY_RC4, b"neteasecloudmusic" + rc4_key)
    encrypted_key = bytes(value ^ _RC4_XOR for value in encrypted_key)
    metadata_bytes = b"music:" + json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    encrypted_metadata = _METADATA_PREFIX + base64.b64encode(
        _aes_encrypt(_AES_KEY_METADATA, metadata_bytes)
    )
    encrypted_metadata = bytes(value ^ _METADATA_XOR for value in encrypted_metadata)
    encrypted_audio = _reference_ncm_xor(audio_bytes, rc4_key)
    destination.write_bytes(
        b"".join(
            [
                NCM_MAGIC,
                b"\x00\x00",
                len(encrypted_key).to_bytes(4, "little"),
                encrypted_key,
                len(encrypted_metadata).to_bytes(4, "little"),
                encrypted_metadata,
                b"\x00\x00\x00\x00",
                b"\x00" * 5,
                len(cover).to_bytes(4, "little"),
                cover,
                encrypted_audio,
            ]
        )
    )


@pytest.mark.parametrize(
    "output_format",
    ["mp3", "flac", "wav", "m4a", "alac", "ogg", "opus", "wma", "aiff"],
)
def test_common_audio_outputs(
    tmp_path: Path,
    tools: ToolPaths,
    output_format: str,
) -> None:
    """Common audio outputs should be playable and retain normalized tags."""
    source = tmp_path / "测试歌手 - 测试音频.wav"
    _make_wave(tools, source)
    output_dir = tmp_path / "output"
    options = ConversionOptions(
        output_dir=output_dir,
        output_format=output_format,
        bitrate_kbps=320,
        fetch_lyrics=False,
        overwrite_policy=OverwritePolicy.RENAME,
    )
    engine = ConversionEngine(options, ffmpeg=FFmpeg(tools))
    result = engine.convert(source)
    assert result.status is JobStatus.SUCCESS, result.message
    assert result.output_path is not None
    assert result.output_path.suffix == f".{OUTPUT_EXTENSIONS[output_format]}"
    info = FFmpeg(tools).probe(result.output_path)
    assert info.duration > 1.0
    if output_format == "mp3":
        assert info.bitrate >= 300_000
    assert result.metadata is not None
    read_back = read_metadata(result.output_path, info)
    assert read_back.title == "测试音频"
    assert read_back.artists == ["测试歌手"]


def test_ape_output_round_trip(tmp_path: Path, tools: ToolPaths) -> None:
    """APE output should be generated through the official Monkey's Audio CLI."""
    if not tools.mac:
        pytest.skip("Monkey's Audio is not installed")
    source = tmp_path / "测试歌手 - APE测试.wav"
    _make_wave(tools, source)
    options = ConversionOptions(
        output_dir=tmp_path / "ape-output",
        output_format="ape",
        fetch_lyrics=False,
    )
    result = ConversionEngine(options, ffmpeg=FFmpeg(tools)).convert(source)
    assert result.status is JobStatus.SUCCESS, result.message
    assert result.output_path and result.output_path.is_file()
    info = FFmpeg(tools).probe(result.output_path)
    assert info.codec_name == "ape"


def test_local_lrc_is_copied_to_output(tmp_path: Path, tools: ToolPaths) -> None:
    """A local timed LRC should become a UTF-8 sidecar without network access."""
    source = tmp_path / "测试歌手 - 歌词测试.wav"
    _make_wave(tools, source)
    source.with_suffix(".lrc").write_text(
        "[ti:歌词测试]\n[00:00.20]第一句\n[00:00.80]第二句\n",
        encoding="utf-8",
    )
    options = ConversionOptions(
        output_dir=tmp_path / "lyrics-output",
        output_format="mp3",
        fetch_lyrics=True,
    )
    result = ConversionEngine(options, ffmpeg=FFmpeg(tools)).convert(source)
    assert result.status is JobStatus.SUCCESS, result.message
    assert result.lrc_path is not None
    assert result.lrc_path.is_file()
    assert "第一句" in result.lrc_path.read_text(encoding="utf-8")


def test_ncm_pipeline_end_to_end(tmp_path: Path, tools: ToolPaths) -> None:
    """A valid NCM should decrypt, merge metadata, transcode, and retain cover art."""
    wave = tmp_path / "fixture.wav"
    _make_wave(tools, wave)
    mp3 = tmp_path / "fixture.mp3"
    result = subprocess.run(
        [
            str(tools.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(wave),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(mp3),
            "-y",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    cover_stream = BytesIO()
    Image.new("RGB", (8, 8), (23, 59, 87)).save(cover_stream, format="PNG")
    source = tmp_path / "fixture.ncm"
    _wrap_ncm(
        source,
        audio_bytes=mp3.read_bytes(),
        cover=cover_stream.getvalue(),
        metadata={
            "format": "mp3",
            "musicId": 10001,
            "musicName": "NCM歌曲",
            "artist": [["NCM歌手", 1]],
            "album": "NCM专辑",
            "genre": "测试风格",
            "duration": 1500,
            "bitrate": 320000,
        },
    )
    source.with_suffix(".lrc").write_text(
        "[00:00.20]NCM 本地歌词\n",
        encoding="utf-8",
    )
    options = ConversionOptions(
        output_dir=tmp_path / "ncm-output",
        output_format="mp3",
        bitrate_kbps=320,
        fetch_lyrics=False,
    )
    converted = ConversionEngine(options, ffmpeg=FFmpeg(tools)).convert(source)
    assert converted.status is JobStatus.SUCCESS, converted.message
    assert converted.output_path is not None
    assert converted.output_path.name == "NCM歌手 - NCM歌曲.mp3"
    info = FFmpeg(tools).probe(converted.output_path)
    tags = read_metadata(converted.output_path, info)
    assert tags.title == "NCM歌曲"
    assert tags.artists == ["NCM歌手"]
    assert tags.album == "NCM专辑"
    assert tags.cover_data
    assert converted.lrc_path is not None
    assert "NCM 本地歌词" in converted.lrc_path.read_text(encoding="utf-8")

