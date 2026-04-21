from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from btb_browser.transcripts import read_transcript_text


@dataclass(slots=True)
class TranscriptCue:
    start_time_raw: str
    start_time_display: str
    speaker_name: str | None
    speaker_color_class: str | None
    text: str


@dataclass(slots=True)
class EpisodeRecord:
    id: int
    title: str
    description: str
    start_date: str
    duration: int | None
    image_url: str
    podcast_slug: str
    transcription_available: bool
    transcript_text: str
    transcript_cues: list[TranscriptCue]
    raw_episode: dict[str, Any]
    search_text: str
    score: int = 0


_WHITESPACE_RE = re.compile(r"\s+")
_SRT_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")
_SRT_TIME_RE = re.compile(r"^(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})(?:[,\.](?P<millis>\d{3}))?$")
_SPEAKER_PREFIX_RE = re.compile(r"^(?P<speaker>[A-Za-z][A-Za-z0-9 .&'()_-]{0,60}?):\s*(?P<text>.+)$")
_SPEAKER_COLOR_CLASSES = (
    "speaker-color-1",
    "speaker-color-2",
    "speaker-color-3",
    "speaker-color-4",
    "speaker-color-5",
    "speaker-color-6",
)


class _DescriptionHTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def _stringify_parts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_stringify_parts(item))
        return parts
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            parts.extend(_stringify_parts(item))
        return parts
    return []


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def clean_description(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    stripper = _DescriptionHTMLStripper()
    stripper.feed(value)
    stripper.close()
    return _WHITESPACE_RE.sub(" ", stripper.get_text()).strip()


def _build_search_text(raw_episode: dict[str, Any], transcript_text: str) -> str:
    parts = _stringify_parts(raw_episode)
    if transcript_text:
        parts.append(transcript_text)
    return _normalize_text(" ".join(parts))


def _normalize_start_date(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        return value
    return str(value)


def _format_transcript_start_time(value: str) -> str | None:
    match = _SRT_TIME_RE.match(value.strip())
    if match is None:
        return None
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _split_speaker_text(text: str) -> tuple[str | None, str]:
    match = _SPEAKER_PREFIX_RE.match(text)
    if match is None:
        return None, text
    speaker = match.group("speaker").strip()
    spoken_text = match.group("text").strip()
    if not spoken_text:
        return None, text
    return speaker, spoken_text


def parse_transcript_cues(transcript_text: str) -> list[TranscriptCue]:
    normalized_text = transcript_text.replace("\r\n", "\n").strip()
    if not normalized_text:
        return []

    cues: list[TranscriptCue] = []
    speaker_colors: dict[str, str] = {}
    for block in _SRT_BLOCK_SPLIT_RE.split(normalized_text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        if "-->" in lines[0]:
            timing_line = lines[0]
            body_lines = lines[1:]
        elif len(lines) >= 3 and lines[0].isdigit() and "-->" in lines[1]:
            timing_line = lines[1]
            body_lines = lines[2:]
        else:
            continue

        start_time_raw = timing_line.partition("-->")[0].strip()
        start_time_display = _format_transcript_start_time(start_time_raw)
        if start_time_display is None:
            continue

        body_text = _WHITESPACE_RE.sub(" ", " ".join(body_lines)).strip()
        if not body_text:
            continue

        speaker_name, text = _split_speaker_text(body_text)
        speaker_color_class = None
        if speaker_name is not None:
            speaker_color_class = speaker_colors.setdefault(
                speaker_name,
                _SPEAKER_COLOR_CLASSES[len(speaker_colors) % len(_SPEAKER_COLOR_CLASSES)],
            )

        if cues and speaker_name is not None:
            previous_cue = cues[-1]
            if previous_cue.speaker_name == speaker_name:
                previous_cue.text = f"{previous_cue.text} {text}".strip()
                continue

        cues.append(
            TranscriptCue(
                start_time_raw=start_time_raw,
                start_time_display=start_time_display,
                speaker_name=speaker_name,
                speaker_color_class=speaker_color_class,
                text=text,
            )
        )

    return cues


def normalize_episode(raw_episode: dict[str, Any], transcript_text: str) -> EpisodeRecord:
    transcript_cues = parse_transcript_cues(transcript_text)
    return EpisodeRecord(
        id=int(raw_episode["id"]),
        title=raw_episode.get("title", ""),
        description=clean_description(raw_episode.get("description", "")),
        start_date=_normalize_start_date(raw_episode.get("startDate")),
        duration=raw_episode.get("duration"),
        image_url=raw_episode.get("imageUrl", ""),
        podcast_slug=raw_episode.get("podcastSlug", ""),
        transcription_available=bool(raw_episode.get("transcriptionAvailable")),
        transcript_text=transcript_text,
        transcript_cues=transcript_cues,
        raw_episode=raw_episode,
        search_text=_build_search_text(raw_episode, transcript_text),
    )


def _sort_key(record: EpisodeRecord) -> tuple[str, int]:
    return (record.start_date, record.id)


def load_archive(
    episodes_dir: Path = Path("episodes"),
    transcripts_dir: Path = Path("transcripts"),
) -> list[EpisodeRecord]:
    if not episodes_dir.exists():
        return []

    records: list[EpisodeRecord] = []
    for episode_path in sorted(episodes_dir.glob("*.json")):
        raw_episode = json.loads(episode_path.read_text(encoding="utf-8"))
        transcript_text = read_transcript_text(transcripts_dir, episode_path.stem)
        records.append(normalize_episode(raw_episode, transcript_text))

    records.sort(key=_sort_key, reverse=True)
    return records


def _other_search_text(raw_episode: dict[str, Any]) -> str:
    ignored_keys = {
        "id",
        "title",
        "description",
        "startDate",
        "duration",
        "imageUrl",
        "podcastSlug",
        "transcriptionAvailable",
    }
    parts: list[str] = []
    for key, value in raw_episode.items():
        if key in ignored_keys:
            continue
        parts.extend(_stringify_parts(value))
    return _normalize_text(" ".join(parts))


def _match_count(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def _ranking_key(record: EpisodeRecord, terms: list[str]) -> tuple[int, int, int, int, str, int]:
    return (
        _match_count(record.title, terms),
        _match_count(record.description, terms),
        _match_count(record.transcript_text, terms),
        _match_count(_other_search_text(record.raw_episode), terms),
        record.start_date,
        record.id,
    )


def search_records(records: Iterable[EpisodeRecord], query: str) -> list[EpisodeRecord]:
    terms = [term for term in _normalize_text(query).split(" ") if term]
    if not terms:
        return list(records)

    matched: list[EpisodeRecord] = []
    for record in records:
        if all(term in record.search_text for term in terms):
            matched.append(record)

    matched.sort(key=lambda record: _ranking_key(record, terms), reverse=True)
    return matched


def paginate_results(items: list[Any], page: int, page_size: int) -> tuple[list[Any], int]:
    safe_page_size = max(page_size, 1)
    total_pages = max(math.ceil(len(items) / safe_page_size), 1)
    safe_page = max(page, 1)
    if items:
        safe_page = min(safe_page, total_pages)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return items[start:end], total_pages
