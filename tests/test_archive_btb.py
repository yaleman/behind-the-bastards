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


def test_archive_episode_warns_and_continues_when_transcript_fetch_fails(tmp_path):
    episode = {
        "id": 329558837,
        "title": "Part Four: The Phil Spector Episodes",
        "transcriptionAvailable": True,
    }
    counters = archive_btb.make_counters()
    warnings = []

    def fake_fetch_text(url):
        if url.endswith("/#transcription"):
            return (
                '<a href="https://api.omny.fm/orgs/example/clips/clip-id/'
                'transcript?format=SubRip&t=12345">Transcript</a>'
            )
        raise RuntimeError("transcript unavailable")

    archive_btb.archive_episode(
        episode=episode,
        episodes_dir=tmp_path / "episodes",
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=fake_fetch_text,
        counters=counters,
        warn=warnings.append,
    )

    episode_path = tmp_path / "episodes" / "329558837.json"
    transcript_path = tmp_path / "transcripts" / "329558837.srt"

    assert episode_path.exists()
    assert not transcript_path.exists()
    assert counters["episodes_new"] == 1
    assert counters["transcripts_failed"] == 1
    assert counters["transcripts_missing"] == 0
    assert len(warnings) == 1
    assert "329558837" in warnings[0]
    assert json.loads(episode_path.read_text()) == episode
