import importlib.util
import json
from pathlib import Path


def load_archive_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "archive_btb.py"
    spec = importlib.util.spec_from_file_location("archive_btb", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


archive_btb = load_archive_module()


def test_iter_episodes_uses_links_next_as_pagekey():
    calls = []

    def fake_fetch_page(page_key):
        calls.append(page_key)
        if page_key is None:
            return {
                "data": [{"id": 1}, {"id": 2}],
                "links": {"next": "token-1"},
            }
        if page_key == "token-1":
            return {
                "data": [{"id": 3}],
                "links": {},
            }
        raise AssertionError(f"unexpected page_key: {page_key}")

    episodes = list(archive_btb.iter_episodes(fake_fetch_page))

    assert calls == [None, "token-1"]
    assert [episode["id"] for episode in episodes] == [1, 2, 3]


def test_write_text_if_changed_reports_new_updated_and_unchanged(tmp_path):
    target = tmp_path / "episode.json"

    first = archive_btb.write_text_if_changed(target, "first\n")
    second = archive_btb.write_text_if_changed(target, "first\n")
    third = archive_btb.write_text_if_changed(target, "second\n")

    assert first == "new"
    assert second == "unchanged"
    assert third == "updated"
    assert target.read_text() == "second\n"


def test_episode_page_url_uses_full_podcast_slug():
    assert (
        archive_btb.episode_page_url(329558837)
        == "https://www.iheart.com/podcast/105-behind-the-bastards-29236323/episode/x-329558837/#transcription"
    )


def test_extract_transcript_url_returns_omny_srt_url():
    html = """
    <html>
      <body>
        <script>
          const transcript = "https://api.omny.fm/orgs/example/clips/clip-id/transcript?format=SubRip&t=12345";
        </script>
      </body>
    </html>
    """

    assert (
        archive_btb.extract_transcript_url(html)
        == "https://api.omny.fm/orgs/example/clips/clip-id/transcript?format=SubRip&t=12345"
    )


def test_archive_metadata_episode_collects_transcript_jobs(tmp_path):
    counters = archive_btb.make_counters()
    transcript_jobs = []

    archive_btb.archive_metadata_episode(
        episode={
            "id": 329558837,
            "title": "Part Four: The Phil Spector Episodes",
            "transcriptionAvailable": True,
        },
        episodes_dir=tmp_path / "episodes",
        counters=counters,
        transcript_jobs=transcript_jobs,
    )
    archive_btb.archive_metadata_episode(
        episode={
            "id": 1,
            "title": "No Transcript Episode",
            "transcriptionAvailable": False,
        },
        episodes_dir=tmp_path / "episodes",
        counters=counters,
        transcript_jobs=transcript_jobs,
    )

    assert [job.episode_id for job in transcript_jobs] == [329558837]
    assert counters["episodes_new"] == 2
    assert counters["transcripts_missing"] == 1


def test_refresh_transcript_job_returns_new_status(tmp_path):
    def fake_fetch_text(url):
        if url.endswith("/#transcription"):
            return (
                '<a href="https://api.omny.fm/orgs/example/clips/clip-id/'
                'transcript?format=SubRip&t=12345">Transcript</a>'
            )
        return "1\n00:00:00,000 --> 00:00:01,000\nhello\n"

    result = archive_btb.refresh_transcript_job(
        job=archive_btb.TranscriptJob(episode_id=329558837),
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=fake_fetch_text,
    )

    assert result.episode_id == 329558837
    assert result.status == "new"
    assert result.warning is None


def test_refresh_transcript_job_returns_missing_when_link_not_found(tmp_path):
    result = archive_btb.refresh_transcript_job(
        job=archive_btb.TranscriptJob(episode_id=329558837),
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=lambda _: "<html></html>",
    )

    assert result.episode_id == 329558837
    assert result.status == "missing"
    assert result.warning == "episode 329558837: transcript link not found"


def test_refresh_transcript_job_returns_failed_on_exception(tmp_path):
    def fake_fetch_text(_url):
        raise RuntimeError("transcript unavailable")

    result = archive_btb.refresh_transcript_job(
        job=archive_btb.TranscriptJob(episode_id=329558837),
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=fake_fetch_text,
    )

    assert result.episode_id == 329558837
    assert result.status == "failed"
    assert result.warning == "episode 329558837: transcript fetch failed: transcript unavailable"


def test_archive_all_runs_metadata_then_parallel_transcripts(tmp_path):
    pages = [
        {
            "data": [
                {
                    "id": 329558837,
                    "title": "Part Four: The Phil Spector Episodes",
                    "transcriptionAvailable": True,
                },
                {
                    "id": 1,
                    "title": "No Transcript Episode",
                    "transcriptionAvailable": False,
                },
            ],
            "links": {},
        }
    ]
    calls = []

    def fake_fetch_text(url):
        calls.append(("text", url))
        if url.endswith("/#transcription"):
            return (
                '<a href="https://api.omny.fm/orgs/example/clips/clip-id/'
                'transcript?format=SubRip&t=12345">Transcript</a>'
            )
        return "1\n00:00:00,000 --> 00:00:01,000\nhello\n"

    def fake_fetch_json(_url):
        calls.append(("json", "page"))
        return pages.pop(0)

    counters = archive_btb.archive_all(
        episodes_dir=tmp_path / "episodes",
        transcripts_dir=tmp_path / "transcripts",
        fetch_json=fake_fetch_json,
        fetch_text=fake_fetch_text,
        max_transcript_workers=2,
    )

    episode_path = tmp_path / "episodes" / "329558837.json"
    transcript_path = tmp_path / "transcripts" / "329558837.srt.zst"

    assert episode_path.exists()
    assert transcript_path.exists()
    assert counters["episodes_new"] == 2
    assert counters["transcripts_new"] == 1
    assert counters["transcripts_missing"] == 1
    assert json.loads(episode_path.read_text())["id"] == 329558837
    assert calls[0][0] == "json"
    assert any(kind == "text" for kind, _ in calls)
