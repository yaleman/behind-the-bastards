import json
from datetime import datetime, timezone

from btb_browser.data import load_archive, paginate_results, parse_transcript_cues, search_records


def write_episode(path, episode_id, **overrides):
    payload = {
        "id": episode_id,
        "title": f"Episode {episode_id}",
        "description": f"Description {episode_id}",
        "startDate": "2026-04-20T00:00:00Z",
        "duration": 3600,
        "imageUrl": "https://example.com/image.jpg",
        "podcastSlug": "behind-the-bastards",
        "transcriptionAvailable": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_archive_normalizes_epoch_start_date_to_iso_string(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    start_date_ms = 1727154000000
    write_episode(episodes_dir / "1.json", 1, startDate=start_date_ms)

    records = load_archive(episodes_dir, transcripts_dir)

    expected = datetime.fromtimestamp(start_date_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    assert records[0].start_date == expected
    assert isinstance(records[0].start_date, str)


def test_load_archive_merges_episode_and_transcript_files(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "2.json",
        2,
        title="Title Match",
        description="Interesting metadata",
        startDate="2026-04-21T00:00:00Z",
        transcriptionAvailable=True,
    )
    (transcripts_dir / "2.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nTranscript body\n",
        encoding="utf-8",
    )

    records = load_archive(episodes_dir, transcripts_dir)

    assert len(records) == 1
    assert records[0].id == 2
    assert records[0].title == "Title Match"
    assert "Transcript body" in records[0].transcript_text
    assert "interesting metadata" in records[0].search_text
    assert records[0].transcript_cues[0].start_time_display == "00:00"
    assert records[0].transcript_cues[0].text == "Transcript body"


def test_load_archive_sorts_newest_first_and_handles_missing_transcript(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(episodes_dir / "1.json", 1, startDate="2025-01-01T00:00:00Z")
    write_episode(episodes_dir / "2.json", 2, startDate="2026-01-01T00:00:00Z")

    records = load_archive(episodes_dir, transcripts_dir)

    assert [record.id for record in records] == [2, 1]
    assert records[0].transcript_text == ""


def test_search_records_keeps_title_hits_ahead_of_larger_lower_priority_matches(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "1.json",
        1,
        title="Alpha",
        description="metadata",
        startDate="2025-01-01T00:00:00Z",
        transcriptionAvailable=True,
    )
    (transcripts_dir / "1.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nBeta gamma delta epsilon\n",
        encoding="utf-8",
    )

    write_episode(
        episodes_dir / "2.json",
        2,
        title="Neutral",
        description="Alpha beta gamma delta epsilon",
        startDate="2026-01-01T00:00:00Z",
    )

    records = load_archive(episodes_dir, transcripts_dir)
    results = search_records(records, "alpha beta gamma delta epsilon")

    assert [record.id for record in results] == [1, 2]


def test_search_records_requires_all_query_terms(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "10.json",
        10,
        title="Hitler",
        description="Ocean talk",
        transcriptionAvailable=True,
    )
    (transcripts_dir / "10.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nSubmarine discussion\n",
        encoding="utf-8",
    )
    write_episode(episodes_dir / "11.json", 11, title="Hitler only")

    records = load_archive(episodes_dir, transcripts_dir)
    results = search_records(records, "hitler submarine")

    assert [record.id for record in results] == [10]


def test_search_records_prefers_title_match_over_transcript_only_match(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "20.json",
        20,
        title="Napoleon",
        description="metadata",
        startDate="2026-04-21T00:00:00Z",
    )
    write_episode(
        episodes_dir / "21.json",
        21,
        title="Different title",
        description="metadata",
        startDate="2026-04-20T00:00:00Z",
        transcriptionAvailable=True,
    )
    (transcripts_dir / "21.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nNapoleon appears here\n",
        encoding="utf-8",
    )

    records = load_archive(episodes_dir, transcripts_dir)
    results = search_records(records, "napoleon")

    assert [record.id for record in results] == [20, 21]


def test_paginate_results_returns_page_slice_and_page_count():
    items = list(range(1, 121))

    page_items, total_pages = paginate_results(items, page=2, page_size=50)

    assert page_items == list(range(51, 101))
    assert total_pages == 3


def test_paginate_results_clamps_oversized_page_to_last_page():
    items = list(range(1, 6))

    page_items, total_pages = paginate_results(items, page=99, page_size=2)

    assert page_items == [5]
    assert total_pages == 3


def test_paginate_results_handles_nonpositive_page_size():
    items = list(range(1, 4))

    page_items, total_pages = paginate_results(items, page=1, page_size=0)

    assert page_items == [1]
    assert total_pages == 3


def test_parse_transcript_cues_extracts_speaker_and_compact_time():
    cues = parse_transcript_cues(
        "\n".join(
            [
                "1",
                "00:00:05,200 --> 00:00:07,000",
                "Speaker 2: Hello there",
                "",
                "2",
                "01:02:03,400 --> 01:02:07,000",
                "Narrator: Another line",
                "",
            ]
        )
    )

    assert [cue.start_time_display for cue in cues] == ["00:05", "1:02:03"]
    assert cues[0].speaker_name == "Speaker 2"
    assert cues[0].text == "Hello there"
    assert cues[0].speaker_color_class == "speaker-color-1"
    assert cues[1].speaker_name == "Narrator"
    assert cues[1].speaker_color_class == "speaker-color-2"


def test_parse_transcript_cues_reuses_color_for_repeat_speakers_in_first_seen_order():
    cues = parse_transcript_cues(
        "\n".join(
            [
                "1",
                "00:00:01,000 --> 00:00:02,000",
                "Speaker 3: First",
                "",
                "2",
                "00:00:03,000 --> 00:00:04,000",
                "Speaker 9: Second",
                "",
                "3",
                "00:00:05,000 --> 00:00:06,000",
                "Speaker 3: Third",
                "",
            ]
        )
    )

    assert [cue.speaker_color_class for cue in cues] == [
        "speaker-color-1",
        "speaker-color-2",
        "speaker-color-1",
    ]


def test_parse_transcript_cues_handles_missing_speaker_and_skips_bad_blocks():
    cues = parse_transcript_cues(
        "\n".join(
            [
                "1",
                "00:00:01,000 --> 00:00:02,000",
                "No speaker line here",
                "",
                "this block is malformed",
                "",
                "2",
                "00:00:03,000 --> 00:00:04,000",
                "Speaker 4: Valid line",
                "",
            ]
        )
    )

    assert len(cues) == 2
    assert cues[0].speaker_name is None
    assert cues[0].speaker_color_class is None
    assert cues[0].text == "No speaker line here"
    assert cues[1].speaker_name == "Speaker 4"


def test_parse_transcript_cues_returns_empty_for_unparseable_text():
    assert parse_transcript_cues("plain transcript without srt timing") == []
