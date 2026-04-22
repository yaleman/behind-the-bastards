from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any, Callable, NamedTuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from btb_browser.transcripts import transcript_storage_path, write_transcript_text_if_changed

PODCAST_ID = 29236323
PODCAST_SLUG = "105-behind-the-bastards-29236323"
EPISODE_API_URL = f"https://au.api.iheart.com/api/v3/podcast/podcasts/{PODCAST_ID}/episodes"
EPISODE_LIMIT = 100
DEFAULT_TRANSCRIPT_WORKERS = 16
TRANSCRIPT_URL_PATTERN = re.compile(
    r"https://api\.omny\.fm/[^\"']+/transcript\?format=SubRip[^\"']*"
)
DEFAULT_HEADERS = {
    "User-Agent": "behind-the-bastards-archiver/0.1",
}


class TranscriptJob(NamedTuple):
    episode_id: int


class TranscriptResult(NamedTuple):
    episode_id: int
    status: str
    warning: str | None = None


def build_episode_api_url(page_key: str | None = None, limit: int = EPISODE_LIMIT) -> str:
    params = {
        "newEnabled": "false",
        "limit": str(limit),
        "sortBy": "startDate-desc",
    }
    if page_key:
        params["pageKey"] = page_key
    return f"{EPISODE_API_URL}?{urlencode(params)}"


def fetch_json_url(url: str) -> dict[str, Any]:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_text_url(url: str) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def fetch_episode_page(
    page_key: str | None,
    fetch_json: Callable[[str], dict[str, Any]] = fetch_json_url,
) -> dict[str, Any]:
    return fetch_json(build_episode_api_url(page_key=page_key))


def iter_episodes(
    fetch_page: Callable[[str | None], dict[str, Any]],
):
    current_page_key: str | None = None
    seen_page_keys: set[str] = set()

    while True:
        page = fetch_page(current_page_key)
        yield from page.get("data", [])

        next_page_key = page.get("links", {}).get("next")
        if not next_page_key or next_page_key in seen_page_keys:
            return

        seen_page_keys.add(next_page_key)
        current_page_key = next_page_key


def make_counters() -> dict[str, int]:
    return {
        "episodes_new": 0,
        "episodes_updated": 0,
        "episodes_unchanged": 0,
        "transcripts_new": 0,
        "transcripts_updated": 0,
        "transcripts_unchanged": 0,
        "transcripts_missing": 0,
        "transcripts_failed": 0,
    }


def serialize_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_text_if_changed(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")
        return "new"

    existing = path.read_text(encoding="utf-8")
    if existing == content:
        return "unchanged"

    path.write_text(content, encoding="utf-8")
    return "updated"


def episode_page_url(episode_id: int) -> str:
    return (
        f"https://www.iheart.com/podcast/{PODCAST_SLUG}/episode/"
        f"x-{episode_id}/#transcription"
    )


def extract_transcript_url(html: str) -> str | None:
    match = TRANSCRIPT_URL_PATTERN.search(html)
    if match is None:
        return None
    return unescape(match.group(0))


def archive_metadata_episode(
    episode: dict[str, Any],
    episodes_dir: Path,
    counters: dict[str, int],
    transcript_jobs: list[TranscriptJob],
) -> dict[str, str]:
    episode_id = episode["id"]
    episode_path = episodes_dir / f"{episode_id}.json"
    episode_status = write_text_if_changed(episode_path, serialize_json(episode))
    counters[f"episodes_{episode_status}"] += 1

    if episode.get("transcriptionAvailable"):
        transcript_jobs.append(TranscriptJob(episode_id=episode_id))
        transcript_status = "queued"
    else:
        counters["transcripts_missing"] += 1
        transcript_status = "missing"

    return {"episode": episode_status, "transcript": transcript_status}


def refresh_transcript_job(
    job: TranscriptJob,
    transcripts_dir: Path,
    fetch_text: Callable[[str], str] = fetch_text_url,
) -> TranscriptResult:
    try:
        html = fetch_text(episode_page_url(job.episode_id))
        transcript_url = extract_transcript_url(html)
        if transcript_url is None:
            return TranscriptResult(
                episode_id=job.episode_id,
                status="missing",
                warning=f"episode {job.episode_id}: transcript link not found",
            )

        transcript_text = fetch_text(transcript_url)
        transcript_path = transcript_storage_path(transcripts_dir, job.episode_id)
        transcript_status = write_transcript_text_if_changed(transcript_path, transcript_text)
        return TranscriptResult(episode_id=job.episode_id, status=transcript_status)
    except Exception as exc:
        return TranscriptResult(
            episode_id=job.episode_id,
            status="failed",
            warning=f"episode {job.episode_id}: transcript fetch failed: {exc}",
        )


def refresh_transcripts(
    transcript_jobs: list[TranscriptJob],
    transcripts_dir: Path,
    counters: dict[str, int],
    fetch_text: Callable[[str], str],
    warn: Callable[[str], None],
    max_transcript_workers: int,
) -> None:
    if not transcript_jobs:
        return

    max_workers = max(1, max_transcript_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(
                refresh_transcript_job,
                job,
                transcripts_dir,
                fetch_text,
            ): job
            for job in transcript_jobs
        }

        for future in as_completed(future_to_job):
            result = future.result()
            counters[f"transcripts_{result.status}"] += 1
            if result.warning is not None:
                warn(result.warning)
            print(f"Transcript {result.episode_id}: {result.status}")


def default_warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def archive_all(
    episodes_dir: Path = Path("episodes"),
    transcripts_dir: Path = Path("transcripts"),
    fetch_json: Callable[[str], dict[str, Any]] = fetch_json_url,
    fetch_text: Callable[[str], str] = fetch_text_url,
    warn: Callable[[str], None] = default_warn,
    max_transcript_workers: int = DEFAULT_TRANSCRIPT_WORKERS,
) -> dict[str, int]:
    counters = make_counters()
    page_count = 0
    transcript_jobs: list[TranscriptJob] = []

    def fetch_page(page_key: str | None) -> dict[str, Any]:
        nonlocal page_count
        page_count += 1
        print(f"Fetching page {page_count} ({'initial' if page_key is None else page_key})")
        return fetch_episode_page(page_key, fetch_json=fetch_json)

    for index, episode in enumerate(iter_episodes(fetch_page), start=1):
        result = archive_metadata_episode(
            episode=episode,
            episodes_dir=episodes_dir,
            counters=counters,
            transcript_jobs=transcript_jobs,
        )
        print(
            f"Episode {index}: {episode['id']} "
            f"(episode={result['episode']}, transcript={result['transcript']})"
        )

    refresh_transcripts(
        transcript_jobs=transcript_jobs,
        transcripts_dir=transcripts_dir,
        counters=counters,
        fetch_text=fetch_text,
        warn=warn,
        max_transcript_workers=max_transcript_workers,
    )

    print("Summary:")
    for key, value in counters.items():
        print(f"  {key}={value}")
    return counters


def main() -> int:
    archive_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
