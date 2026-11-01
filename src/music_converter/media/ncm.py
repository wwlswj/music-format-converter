"""Local parser for NetEase Cloud Music ``.ncm`` container files.

The container format and initial implementation were informed by the MIT-licensed
``ncmdump-py 1.1.6`` project by ww-rm. This project uses a bounded, streaming
adapter and intentionally excludes its network, logging, and tag-writing paths.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from Crypto.Util.strxor import strxor
from PIL import Image

from music_converter.models import TrackMetadata

NCM_MAGIC = b"CTENFDAM"
_AES_KEY_RC4 = bytes.fromhex("687A4852416D736F356B496E62617857")
_AES_KEY_METADATA = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")
_RC4_XOR = 0x64
_METADATA_XOR = 0x63
_METADATA_PREFIX = b"163 key(Don't modify):"
_KEY_PREFIX = b"neteasecloudmusic"
_MAX_FIELD_SIZE = 64 * 1024 * 1024
_DECRYPT_CHUNK_SIZE = 4 * 1024 * 1024


class NcmError(RuntimeError):
    """Base exception for NCM parsing and extraction failures."""


class NcmFormatError(NcmError):
    """Raised when the NCM container has an invalid structure."""


class NcmCryptoError(NcmError):
    """Raised when an NCM cryptographic field cannot be decoded."""


@dataclass(slots=True)
class NcmContainer:
    """Parsed NCM metadata and the location of encrypted audio data."""

    path: Path
    audio_offset: int
    audio_size: int
    rc4_key: bytes
    metadata: TrackMetadata
    cover_data: bytes | None = None
    raw_metadata: dict = field(default_factory=dict)

    @property
    def original_extension(self) -> str:
        """Return the best-known extension of the encrypted underlying audio."""
        extension = self.metadata.source_format.lower().lstrip(".")
        if extension in {"mp3", "flac", "aac", "m4a", "wav", "ogg", "opus"}:
            return extension
        return "mp3"


class _NcmRc4:
    """Generate the fixed repeating 256-byte NCM XOR mask."""

    def __init__(self, key: bytes) -> None:
        if not key:
            raise NcmCryptoError("NCM 音频密钥为空。")
        state = bytearray(range(256))
        key_box = bytearray(256)
        key_index = 0
        for index in range(256):
            # The key cursor advances once per state index; it is not the
            # rolling RC4 swap index used in the state update below.
            key_byte = key[index % len(key)]
            key_index = (key_index + state[index] + key_byte) & 0xFF
            state[index], state[key_index] = state[key_index], state[index]

        for index in range(256):
            cursor = (index + 1) & 0xFF
            value = state[cursor]
            mixed = state[(value + cursor) & 0xFF]
            key_box[index] = state[(mixed + value) & 0xFF]
        self._mask = bytes(key_box)

    def xor(self, data: bytes) -> bytes:
        """XOR a chunk with the repeating mask."""
        repeats = (len(data) + 255) // 256
        mask = (self._mask * repeats)[: len(data)]
        return strxor(data, mask)


def _read_exact(stream: BinaryIO, size: int, field: str) -> bytes:
    """Read exactly ``size`` bytes or raise a descriptive format error."""
    if size < 0 or size > _MAX_FIELD_SIZE:
        raise NcmFormatError(f"{field} 长度异常：{size}")
    data = stream.read(size)
    if len(data) != size:
        raise NcmFormatError(f"{field} 数据不完整。")
    return data


def _read_u32(stream: BinaryIO, field: str) -> int:
    """Read a little-endian unsigned 32-bit integer."""
    return int.from_bytes(_read_exact(stream, 4, field), "little")


def _aes_decrypt(key: bytes, payload: bytes) -> bytes:
    """Decrypt and PKCS#7-unpad an AES-ECB payload."""
    if not payload or len(payload) % 16:
        raise NcmCryptoError("AES 字段长度不是 16 字节的倍数。")
    try:
        decrypted = AES.new(key, AES.MODE_ECB).decrypt(payload)
        return unpad(decrypted, 16)
    except (ValueError, IndexError) as exc:
        raise NcmCryptoError("AES 字段解密或去填充失败。") from exc


def _decode_audio_key(encrypted: bytes) -> bytes:
    """Decode the per-file NCM audio key."""
    xored = bytes(byte ^ _RC4_XOR for byte in encrypted)
    decoded = _aes_decrypt(_AES_KEY_RC4, xored)
    if decoded.startswith(_KEY_PREFIX):
        decoded = decoded[len(_KEY_PREFIX) :]
    if not decoded:
        raise NcmCryptoError("NCM 音频密钥解析结果为空。")
    return decoded


def _decode_metadata(encrypted: bytes) -> dict:
    """Decode the optional embedded JSON metadata."""
    if not encrypted:
        return {}
    xored = bytes(byte ^ _METADATA_XOR for byte in encrypted)
    if not xored.startswith(_METADATA_PREFIX):
        raise NcmCryptoError("NCM 元数据前缀不匹配。")
    try:
        base64_payload = base64.b64decode(xored[len(_METADATA_PREFIX) :], validate=True)
    except (ValueError, TypeError) as exc:
        raise NcmCryptoError("NCM 元数据 Base64 解码失败。") from exc
    plain = _aes_decrypt(_AES_KEY_METADATA, base64_payload)
    try:
        text = plain.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NcmCryptoError("NCM 元数据不是有效 UTF-8。") from exc

    if ":" not in text:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise NcmCryptoError("NCM 元数据 JSON 无效。") from exc

    metadata_type, json_text = text.split(":", 1)
    if metadata_type not in {"music", "dj"}:
        raise NcmCryptoError(f"未知 NCM 元数据类型：{metadata_type}")
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise NcmCryptoError("NCM 元数据 JSON 无效。") from exc
    if metadata_type == "dj":
        parsed = parsed.get("mainMusic", parsed)
    return parsed if isinstance(parsed, dict) else {}


def _find_text(mapping: dict, keys: tuple[str, ...]) -> str:
    """Find the first non-empty string value among candidate keys."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = _find_text(value, ("lyric", "lyrics", "text", "content", "lrc"))
            if nested:
                return nested
    return ""


def _artist_names(raw: object) -> list[str]:
    """Normalize NetEase's nested or string artist representation."""
    names: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                names.append(item[0].strip())
            elif isinstance(item, dict):
                value = item.get("name")
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
    elif isinstance(raw, str) and raw.strip():
        names.extend(part.strip() for part in re.split(r"[/;,]", raw) if part.strip())
    return list(dict.fromkeys(name for name in names if name))


def _cover_mime(data: bytes) -> str:
    """Infer a cover MIME type using image headers handled by Pillow."""
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = (image.format or "").lower()
    except Exception:
        return ""
    return {
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "bmp": "image/bmp",
    }.get(image_format, f"image/{image_format}" if image_format else "")


def _metadata_from_dict(data: dict) -> TrackMetadata:
    """Convert raw NetEase metadata into the application's normalized model."""
    duration_raw = data.get("duration", 0)
    try:
        duration = float(duration_raw) / 1000.0 if duration_raw else 0.0
    except (TypeError, ValueError):
        duration = 0.0
    try:
        bitrate = int(data.get("bitrate", 0) or 0)
    except (TypeError, ValueError):
        bitrate = 0
    source_id_raw = data.get("musicId")
    try:
        source_id = int(source_id_raw) if source_id_raw is not None else None
    except (TypeError, ValueError):
        source_id = None

    return TrackMetadata(
        title=str(data.get("musicName") or data.get("name") or ""),
        artists=_artist_names(data.get("artist") or data.get("artists") or []),
        album=str(data.get("album") or data.get("albumName") or ""),
        genre=str(data.get("genre") or data.get("genreName") or ""),
        duration=duration,
        bitrate=bitrate,
        source_format=str(data.get("format") or ""),
        source_id=source_id,
        embedded_lyrics=_find_text(
            data,
            ("lyric", "lyrics", "lrc", "lyricText", "originalLyric"),
        ),
        translated_lyrics=_find_text(
            data,
            ("translatedLyric", "translation", "tlyric", "trans"),
        ),
        raw_metadata=data,
    )


def parse_ncm(path: str | Path) -> NcmContainer:
    """Parse an NCM header without loading the encrypted audio into memory."""
    source = Path(path)
    try:
        stream = source.open("rb")
    except OSError as exc:
        raise NcmError(f"无法打开 NCM 文件：{source}") from exc

    try:
        with stream:
            if _read_exact(stream, 8, "文件头") != NCM_MAGIC:
                raise NcmFormatError("文件头不是 CTENFDAM，可能不是有效 NCM。")
            _read_exact(stream, 2, "预留字段")

            encrypted_key = _read_exact(
                stream,
                _read_u32(stream, "音频密钥长度"),
                "音频密钥",
            )
            encrypted_metadata = _read_exact(
                stream,
                _read_u32(stream, "元数据长度"),
                "元数据",
            )
            rc4_key = _decode_audio_key(encrypted_key)
            raw_metadata = _decode_metadata(encrypted_metadata)

            _read_u32(stream, "音频 CRC")
            _read_exact(stream, 5, "预留字段")
            cover_length = _read_u32(stream, "封面长度")
            cover = _read_exact(stream, cover_length, "封面") if cover_length else b""
            audio_offset = stream.tell()
            audio_size = source.stat().st_size - audio_offset
            if audio_size <= 0:
                raise NcmFormatError("NCM 文件中没有音频数据。")
    except OSError as exc:
        raise NcmError(f"读取 NCM 文件失败：{source}") from exc

    metadata = _metadata_from_dict(raw_metadata)
    metadata.cover_data = cover or None
    metadata.cover_mime = _cover_mime(cover) if cover else ""
    return NcmContainer(
        path=source,
        audio_offset=audio_offset,
        audio_size=audio_size,
        rc4_key=rc4_key,
        metadata=metadata,
        cover_data=cover or None,
        raw_metadata=raw_metadata,
    )


def decrypt_ncm_audio(container: NcmContainer, destination: str | Path) -> Path:
    """Decrypt NCM audio data to ``destination`` in bounded chunks."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    masker = _NcmRc4(container.rc4_key)
    remaining = container.audio_size
    temporary = target.with_name(f".{target.name}.part")

    try:
        with container.path.open("rb") as source, temporary.open("wb") as output:
            source.seek(container.audio_offset)
            while remaining:
                chunk = source.read(min(_DECRYPT_CHUNK_SIZE, remaining))
                if not chunk:
                    raise NcmFormatError("NCM 音频数据在预期结束前中断。")
                output.write(masker.xor(chunk))
                remaining -= len(chunk)
            output.flush()
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise NcmError(f"写出 NCM 解密音频失败：{target}") from exc
    except NcmError:
        temporary.unlink(missing_ok=True)
        raise
    return target

