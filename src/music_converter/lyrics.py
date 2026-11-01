"""Lyrics discovery, normalization, matching, and local caching."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import httpx
from rapidfuzz import fuzz

from music_converter import __version__
from music_converter.config import lyrics_cache_path
from music_converter.models import (
    LyricsCandidate,
    LyricsResolution,
    LyricsStatus,
    TrackMetadata,
)

_TIMESTAMP_RE = re.compile(r"\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?]")
_INSTRUMENTAL_HINT_RE = re.compile(
    r"\b(?:instrumental|inst\.?|off[ -]?vocal|karaoke)\b|纯音乐|伴奏|无人声",
    re.IGNORECASE,
)
_LRCLIB_REQUEST_LOCK = threading.Lock()
_LRCLIB_LAST_REQUEST = 0.0


class LyricsError(RuntimeError):
    """Raised when an online lyrics request fails."""


def normalize_match_text(value: str) -> str:
    """Normalize title or artist text for fuzzy matching."""
    text = value.casefold()
    text = re.sub(r"\((?:feat\.?|ft\.?|with)[^)]*\)", "", text, flags=re.I)
    text = re.sub(r"\[(?:feat\.?|ft\.?|with)[^]]*]", "", text, flags=re.I)
    text = re.sub(r"\b(?:remastered|remaster|live|acoustic|version|edit)\b", "", text)
    text = re.sub(r"[^\w\u3400-\u9fff]+", "", text, flags=re.UNICODE)
    return text.strip()


def has_lrc_timestamps(text: str) -> bool:
    """Return whether text contains at least one LRC timestamp."""
    return bool(_TIMESTAMP_RE.search(text or ""))


def normalize_lrc(text: str) -> str:
    """Normalize line endings and surrounding whitespace."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


def make_unsynced_lrc(text: str, metadata: TrackMetadata) -> str:
    """Wrap plain lyrics as an explicitly unsynchronized LRC sidecar."""
    header = [
        f"[ti:{metadata.title}]" if metadata.title else "",
        f"[ar:{metadata.artist_text}]" if metadata.artist_text else "",
        f"[al:{metadata.album}]" if metadata.album else "",
        "[re:MusicFormatConverter]",
        "[ve:unsynced]",
    ]
    body = normalize_lrc(text).splitlines()
    return normalize_lrc("\n".join([line for line in header if line] + body))


def merge_translated_lyrics(original: str, translated: str) -> str:
    """Merge timestamps from a translated LRC into the original LRC when possible."""
    if not original or not translated or not has_lrc_timestamps(original):
        return normalize_lrc(original)
    if not has_lrc_timestamps(translated):
        return normalize_lrc(original)

    translation_by_time: dict[str, list[str]] = {}
    for line in translated.replace("\r\n", "\n").splitlines():
        matches = list(_TIMESTAMP_RE.finditer(line))
        if not matches:
            continue
        content = line[matches[-1].end() :].strip()
        if not content:
            continue
        for match in matches:
            translation_by_time.setdefault(match.group(0), []).append(content)

    merged: list[str] = []
    for line in original.replace("\r\n", "\n").splitlines():
        matches = list(_TIMESTAMP_RE.finditer(line))
        if not matches:
            merged.append(line)
            continue
        content = line[matches[-1].end() :].strip()
        translated_parts = translation_by_time.get(matches[-1].group(0), [])
        if translated_parts and translated_parts[0] != content:
            prefix = "".join(match.group(0) for match in matches)
            merged.append(f"{prefix}{content} / {translated_parts[0]}")
        else:
            merged.append(line)
    return normalize_lrc("\n".join(merged))


def find_local_lrc(source_path: Path) -> Path | None:
    """Find a sibling ``.lrc`` file using Windows-friendly case-insensitive lookup."""
    direct = source_path.with_suffix(".lrc")
    if direct.is_file():
        return direct
    try:
        basename = source_path.stem.casefold()
        for entry in source_path.parent.iterdir():
            if (
                entry.is_file()
                and entry.suffix.casefold() == ".lrc"
                and entry.stem.casefold() == basename
            ):
                return entry
    except OSError:
        return None
    return None


def read_lrc_file(path: Path) -> str:
    """Read common UTF-8, UTF-16, or Chinese GB18030 LRC encodings."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for encoding in ("utf-8-sig", "gb18030", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class LyricsCache:
    """SQLite-backed cache for lyric resolutions."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Create a cache bound to ``path``."""
        self.path = Path(path) if path else lyrics_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prepare()

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived SQLite connection."""
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _prepare(self) -> None:
        """Create the cache schema if needed."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lyrics_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )

    @staticmethod
    def make_key(metadata: TrackMetadata) -> str:
        """Build a stable cache key from normalized track identity."""
        identity = "|".join(
            [
                normalize_match_text(metadata.title),
                normalize_match_text(metadata.artist_text),
                normalize_match_text(metadata.album),
                str(round(metadata.duration)),
            ]
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def get(self, metadata: TrackMetadata) -> LyricsResolution | None:
        """Return a cached resolution when present."""
        key = self.make_key(metadata)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM lyrics_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"])
            candidates = [
                LyricsCandidate(**candidate) for candidate in payload.pop("candidates", [])
            ]
            payload["status"] = LyricsStatus(payload["status"])
            return LyricsResolution(candidates=candidates, **payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def set(self, metadata: TrackMetadata, resolution: LyricsResolution) -> None:
        """Persist a non-error resolution."""
        if resolution.status is LyricsStatus.ERROR:
            return
        payload = asdict(resolution)
        serialized = json.dumps(payload, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO lyrics_cache(cache_key, payload, created_at)
                VALUES(?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload = excluded.payload,
                    created_at = excluded.created_at
                """,
                (self.make_key(metadata), serialized, int(time.time())),
            )


class LrclibClient:
    """Client for the documented LRCLIB lyrics API."""

    def __init__(self, timeout: float = 8.0, delay_seconds: float = 0.25) -> None:
        """Create a client with polite request defaults."""
        self.timeout = timeout
        self.delay_seconds = delay_seconds
        contact = os.environ.get("MUSIC_CONVERTER_CONTACT", "local desktop use")
        self.headers = {
            "User-Agent": f"MusicFormatConverter/{__version__} ({contact})",
            "Accept": "application/json",
        }

    def _get(self, client: httpx.Client, path: str, params: dict) -> dict | list | None:
        """Perform one request with a single bounded rate-limit retry."""
        global _LRCLIB_LAST_REQUEST
        for attempt in range(2):
            with _LRCLIB_REQUEST_LOCK:
                elapsed = time.monotonic() - _LRCLIB_LAST_REQUEST
                if elapsed < self.delay_seconds:
                    time.sleep(self.delay_seconds - elapsed)
                try:
                    response = client.get(path, params=params)
                except httpx.HTTPError as exc:
                    raise LyricsError(f"LRCLIB 网络请求失败：{exc}") from exc
                _LRCLIB_LAST_REQUEST = time.monotonic()
            if response.status_code == 404:
                return None
            if response.status_code == 429 and attempt == 0:
                retry_after = response.headers.get("Retry-After", "2")
                try:
                    delay = min(max(float(retry_after), 0.5), 5.0)
                except ValueError:
                    delay = 2.0
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise LyricsError(f"LRCLIB 返回 HTTP {response.status_code}。")
            try:
                return response.json()
            except ValueError as exc:
                raise LyricsError("LRCLIB 返回了无效 JSON。") from exc
        return None

    @staticmethod
    def _candidate(item: dict) -> LyricsCandidate:
        """Convert a LRCLIB record into the internal candidate type."""
        return LyricsCandidate(
            provider="LRCLIB",
            provider_id=str(item.get("id", "")),
            track_name=str(item.get("trackName") or item.get("name") or ""),
            artist_name=str(item.get("artistName") or ""),
            album_name=str(item.get("albumName") or ""),
            duration=float(item.get("duration") or 0.0),
            synced_lyrics=str(item.get("syncedLyrics") or ""),
            plain_lyrics=str(item.get("plainLyrics") or ""),
            instrumental=bool(item.get("instrumental", False)),
        )

    @staticmethod
    def _score(metadata: TrackMetadata, candidate: LyricsCandidate) -> float:
        """Compute a conservative 0-1 match score."""
        title_score = fuzz.token_set_ratio(
            normalize_match_text(metadata.title),
            normalize_match_text(candidate.track_name),
        )
        artist_score = fuzz.token_set_ratio(
            normalize_match_text(metadata.artist_text),
            normalize_match_text(candidate.artist_name),
        )
        album_score = fuzz.token_set_ratio(
            normalize_match_text(metadata.album),
            normalize_match_text(candidate.album_name),
        )
        duration_delta = abs(metadata.duration - candidate.duration)
        duration_score = max(0.0, 100.0 - duration_delta * 20.0)
        return round(
            (title_score * 0.52 + artist_score * 0.30 + album_score * 0.08 + duration_score * 0.10)
            / 100.0,
            4,
        )

    def find_candidates(self, metadata: TrackMetadata) -> list[LyricsCandidate]:
        """Query exact signature first, then fall back to keyword search."""
        if not metadata.title:
            return []
        params: dict[str, str | int] = {"track_name": metadata.title}
        if metadata.artist_text:
            params["artist_name"] = metadata.artist_text
        if metadata.album:
            params["album_name"] = metadata.album
        if 1 <= metadata.duration <= 3600:
            params["duration"] = round(metadata.duration)

        with httpx.Client(
            base_url="https://lrclib.net",
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            exact = self._get(client, "/api/get", params)
            items: list[dict] = []
            if isinstance(exact, dict):
                items.append(exact)
            elif metadata.title:
                time.sleep(self.delay_seconds)
                search_params: dict[str, str] = {"track_name": metadata.title}
                if metadata.artist_text:
                    search_params["artist_name"] = metadata.artist_text
                response = self._get(client, "/api/search", search_params)
                if isinstance(response, list):
                    items.extend(item for item in response if isinstance(item, dict))

        candidates = [self._candidate(item) for item in items]
        for candidate in candidates:
            candidate.confidence = self._score(metadata, candidate)
        candidates.sort(key=lambda item: item.confidence, reverse=True)
        return candidates[:5]


class LyricsResolver:
    """Resolve lyrics according to embedded, sidecar, and online precedence."""

    def __init__(
        self,
        cache: LyricsCache | None = None,
        lrclib: LrclibClient | None = None,
        auto_accept_threshold: float = 0.86,
    ) -> None:
        """Create a resolver with optional injected dependencies for tests."""
        self.cache = cache or LyricsCache()
        self.lrclib = lrclib or LrclibClient()
        self.auto_accept_threshold = auto_accept_threshold

    def resolve(
        self,
        source_path: Path,
        metadata: TrackMetadata,
        *,
        fetch_online: bool,
        allow_unsynced: bool,
    ) -> LyricsResolution:
        """Resolve lyrics using all available sources."""
        embedded = metadata.embedded_lyrics.strip()
        if embedded:
            content = normalize_lrc(embedded)
            final_content = (
                content
                if has_lrc_timestamps(content)
                else make_unsynced_lrc(content, metadata)
            )
            if metadata.translated_lyrics and has_lrc_timestamps(content):
                content = merge_translated_lyrics(content, metadata.translated_lyrics)
                final_content = content
            if has_lrc_timestamps(content) or allow_unsynced:
                return LyricsResolution(
                    status=LyricsStatus.EMBEDDED,
                    provider="音频内嵌",
                    content=final_content,
                    synced=has_lrc_timestamps(content),
                    confidence=1.0,
                )

        local = find_local_lrc(source_path)
        if local:
            try:
                content = normalize_lrc(read_lrc_file(local))
            except (OSError, UnicodeError):
                content = ""
            if content and (has_lrc_timestamps(content) or allow_unsynced):
                final_content = (
                    content
                    if has_lrc_timestamps(content)
                    else make_unsynced_lrc(content, metadata)
                )
                return LyricsResolution(
                    status=LyricsStatus.LOCAL_FILE,
                    provider=str(local),
                    content=final_content,
                    synced=has_lrc_timestamps(content),
                    confidence=1.0,
                )

        if not fetch_online:
            return LyricsResolution(
                status=LyricsStatus.NOT_REQUESTED,
                message="未找到内嵌或同名本地 LRC，联网歌词匹配已关闭。",
            )

        if _INSTRUMENTAL_HINT_RE.search(metadata.title):
            return LyricsResolution(
                status=LyricsStatus.INSTRUMENTAL,
                message="标题或标签显示为纯音乐/伴奏。",
                confidence=0.9,
            )

        cached = self.cache.get(metadata)
        if cached:
            return cached

        try:
            candidates = self.lrclib.find_candidates(metadata)
        except LyricsError as exc:
            return LyricsResolution(status=LyricsStatus.ERROR, message=str(exc))

        if not candidates:
            resolution = LyricsResolution(
                status=LyricsStatus.NOT_FOUND,
                message="未在 LRCLIB 找到候选歌词。",
            )
            self.cache.set(metadata, resolution)
            return resolution

        best = candidates[0]
        if best.instrumental:
            resolution = LyricsResolution(
                status=LyricsStatus.INSTRUMENTAL,
                provider=best.provider,
                confidence=best.confidence,
                message="歌词源标记为纯音乐。",
                candidates=candidates,
            )
        elif best.confidence >= self.auto_accept_threshold:
            content = best.synced_lyrics.strip() or best.plain_lyrics.strip()
            synced = bool(best.synced_lyrics.strip())
            if content and (synced or allow_unsynced):
                resolution = LyricsResolution(
                    status=LyricsStatus.ONLINE,
                    provider=best.provider,
                    content=normalize_lrc(content)
                    if synced
                    else make_unsynced_lrc(content, metadata),
                    synced=synced,
                    confidence=best.confidence,
                    candidates=candidates,
                )
            else:
                resolution = LyricsResolution(
                    status=LyricsStatus.PENDING,
                    provider=best.provider,
                    confidence=best.confidence,
                    message="只找到无时间轴歌词，当前设置为不自动写入。",
                    candidates=candidates,
                )
        else:
            resolution = LyricsResolution(
                status=LyricsStatus.PENDING,
                provider=best.provider,
                confidence=best.confidence,
                message="歌词候选置信度不足，等待人工确认。",
                candidates=candidates,
            )
        self.cache.set(metadata, resolution)
        return resolution


def candidate_summary(candidates: Iterable[LyricsCandidate]) -> str:
    """Format a compact human-readable candidate summary."""
    lines = []
    for index, item in enumerate(candidates, start=1):
        lines.append(
            f"{index}. {item.artist_name} - {item.track_name} "
            f"[{item.album_name}] 置信度 {item.confidence:.0%}"
        )
    return "\n".join(lines)

