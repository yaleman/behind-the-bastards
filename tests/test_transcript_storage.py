import importlib.util
import json
from pathlib import Path

from btb_browser.data import load_archive


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


archive_btb = load_module(Path("scripts/archive_btb.py"), "archive_btb")
migrate_transcripts = load_module(Path("scripts/migrate_transcripts_to_zstd.py"), "migrate_transcripts")


def write_episode(path: Path, episode_id: int, **overrides):
    payload = {
        "id": episode_id,
        "title": f"Episode {episode_id}",
        "description": f"Description {episode_id}",
        "startDate": "2026-04-20T00:00:00Z",
        "duration": 3600,
        "imageUrl": "https://example.com/image.jpg",
        "podcastSlug": "behind-the-bastards",
        "transcriptionAvailable": True,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_archive_episode_writes_zstd_transcript_file(tmp_path):
    episode = {
        "id": 329558837,
        "title": "Part Four: The Phil Spector Episodes",
        "transcriptionAvailable": True,
    }

    def fake_fetch_text(url):
        if url.endswith("/#transcription"):
            return (
                '<a href="https://api.omny.fm/orgs/example/clips/clip-id/'
                'transcript?format=SubRip&t=12345">Transcript</a>'
            )
        return "1\n00:00:00,000 --> 00:00:01,000\nTranscript body\n"

    result = archive_btb.archive_episode(
        episode=episode,
        episodes_dir=tmp_path / "episodes",
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=fake_fetch_text,
    )

    assert result["transcript"] == "new"
    assert not (tmp_path / "transcripts" / "329558837.srt").exists()
    assert (tmp_path / "transcripts" / "329558837.srt.zst").exists()


def test_migration_script_converts_legacy_srt_files(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(episodes_dir / "7.json", 7)
    legacy_path = transcripts_dir / "7.srt"
    legacy_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nTranscript body\n", encoding="utf-8")

    summary = migrate_transcripts.migrate_transcripts(transcripts_dir)

    assert summary["transcripts_new"] == 1
    assert not legacy_path.exists()
    assert (transcripts_dir / "7.srt.zst").exists()

    records = load_archive(episodes_dir, transcripts_dir)

    assert records[0].transcript_text == "1\n00:00:00,000 --> 00:00:01,000\nTranscript body\n"
