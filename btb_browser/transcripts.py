from __future__ import annotations

from pathlib import Path

import zstandard as zstd

TRANSCRIPT_SUFFIX = ".srt.zst"
LEGACY_TRANSCRIPT_SUFFIX = ".srt"

_COMPRESSOR = zstd.ZstdCompressor(level=3)
_DECOMPRESSOR = zstd.ZstdDecompressor()


def transcript_storage_path(transcripts_dir: Path, episode_id: int | str) -> Path:
    return transcripts_dir / f"{episode_id}{TRANSCRIPT_SUFFIX}"


def legacy_transcript_path(transcripts_dir: Path, episode_id: int | str) -> Path:
    return transcripts_dir / f"{episode_id}{LEGACY_TRANSCRIPT_SUFFIX}"


def compress_text(content: str) -> bytes:
    return _COMPRESSOR.compress(content.encode("utf-8"))


def decompress_text(content: bytes) -> str:
    return _DECOMPRESSOR.decompress(content).decode("utf-8")


def read_transcript_text(transcripts_dir: Path, episode_id: int | str) -> str:
    compressed_path = transcript_storage_path(transcripts_dir, episode_id)
    if compressed_path.exists():
        return decompress_text(compressed_path.read_bytes())

    legacy_path = legacy_transcript_path(transcripts_dir, episode_id)
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")

    return ""


def write_transcript_text_if_changed(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(compress_text(content))
        return "new"

    existing = decompress_text(path.read_bytes())
    if existing == content:
        return "unchanged"

    path.write_bytes(compress_text(content))
    return "updated"
