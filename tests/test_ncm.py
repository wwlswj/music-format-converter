"""Tests for bounded NCM parsing and streaming decryption."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from PIL import Image

from music_converter.media.ncm import (
    _AES_KEY_METADATA,
    _AES_KEY_RC4,
    _METADATA_PREFIX,
    _METADATA_XOR,
    _RC4_XOR,
    NCM_MAGIC,
    NcmFormatError,
    decrypt_ncm_audio,
    parse_ncm,
)


def _encrypt_aes(key: bytes, payload: bytes) -> bytes:
    """Encrypt a padded payload with AES-ECB for fixture construction."""
    return AES.new(key, AES.MODE_ECB).encrypt(pad(payload, 16))


def _reference_ncm_xor(data: bytes, key: bytes) -> bytes:
    """Apply an independent C++-compatible NCM RC4 variant."""
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


def _build_ncm(
    path: Path,
    *,
    audio: bytes,
    cover: bytes,
    metadata: dict,
) -> bytes:
    """Construct a valid synthetic NCM fixture from plaintext fields."""
    rc4_key = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
    plain_key = b"neteasecloudmusic" + rc4_key
    encrypted_key = _encrypt_aes(_AES_KEY_RC4, plain_key)
    encrypted_key = bytes(byte ^ _RC4_XOR for byte in encrypted_key)

    metadata_plain = b"music:" + json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    encrypted_metadata = base64.b64encode(
        _encrypt_aes(_AES_KEY_METADATA, metadata_plain)
    )
    encrypted_metadata = _METADATA_PREFIX + encrypted_metadata
    encrypted_metadata = bytes(byte ^ _METADATA_XOR for byte in encrypted_metadata)

    audio_ciphertext = _reference_ncm_xor(audio, rc4_key)
    content = b"".join(
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
            audio_ciphertext,
        ]
    )
    path.write_bytes(content)
    return rc4_key


def _png_bytes() -> bytes:
    """Create a tiny valid PNG cover."""
    stream = BytesIO()
    Image.new("RGB", (4, 4), (226, 184, 78)).save(stream, format="PNG")
    return stream.getvalue()


def test_parse_and_stream_decrypt_synthetic_ncm(tmp_path: Path) -> None:
    """The parser must preserve metadata and decrypt audio byte-for-byte."""
    source = tmp_path / "sample.ncm"
    audio = bytes(range(256)) * 40 + b"audio-tail"
    metadata = {
        "format": "mp3",
        "musicId": 123456,
        "musicName": "测试歌曲",
        "artist": [["测试歌手", 42]],
        "album": "测试专辑",
        "genre": "国风",
        "duration": 125000,
        "bitrate": 320000,
        "lyric": "[00:01.00]第一句\n[00:02.00]第二句",
    }
    _build_ncm(
        source,
        audio=audio,
        cover=_png_bytes(),
        metadata=metadata,
    )

    container = parse_ncm(source)
    assert container.metadata.title == "测试歌曲"
    assert container.metadata.artists == ["测试歌手"]
    assert container.metadata.album == "测试专辑"
    assert container.metadata.genre == "国风"
    assert container.metadata.duration == 125
    assert container.metadata.cover_mime == "image/png"
    assert container.audio_size == len(audio)

    output = tmp_path / "decrypted.mp3"
    decrypt_ncm_audio(container, output)
    assert output.read_bytes() == audio
    assert not output.with_name(f".{output.name}.part").exists()


def test_rejects_invalid_ncm_header(tmp_path: Path) -> None:
    """A malformed header should fail with a domain-specific exception."""
    source = tmp_path / "invalid.ncm"
    source.write_bytes(b"NOT-NCM!" + b"\x00" * 32)
    with pytest.raises(NcmFormatError):
        parse_ncm(source)


def test_parser_rejects_truncated_field(tmp_path: Path) -> None:
    """Length fields that point past EOF must not trigger oversized reads."""
    source = tmp_path / "truncated.ncm"
    source.write_bytes(
        NCM_MAGIC + b"\x00\x00" + (1024 * 1024).to_bytes(4, "little")
    )
    with pytest.raises(NcmFormatError):
        parse_ncm(source)

