import json

from fastapi.testclient import TestClient

from btb_browser.web import create_app


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


def test_home_page_clamps_out_of_range_page_in_pagination_ui(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    for episode_id in range(1, 27):
        write_episode(
            episodes_dir / f"{episode_id}.json",
            episode_id,
            title=f"Episode {episode_id}",
            startDate=f"2026-01-{episode_id:02d}T00:00:00Z",
        )

    client = TestClient(create_app(tmp_path))
    response = client.get("/", params={"page": 99})

    assert response.status_code == 200
    assert "Page 2 of 2" in response.text
    assert 'href="/?page=1"' in response.text
    assert "Page 99 of 2" not in response.text


def test_home_page_renders_duration_excerpt_and_pagination_controls(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    for episode_id in range(1, 27):
        write_episode(
            episodes_dir / f"{episode_id}.json",
            episode_id,
            title=f"Episode {episode_id}",
            description="This is a longer description that should be excerpted in the listing view.",
            duration=episode_id * 60,
            startDate=f"2026-01-{episode_id:02d}T00:00:00Z",
        )

    client = TestClient(create_app(tmp_path))
    response = client.get("/", params={"page": 2})

    assert response.status_code == 200
    assert "Page 2 of 2" in response.text
    assert "Previous" in response.text
    assert "Next" not in response.text
    assert "2:00" in response.text
    assert "This is a longer description that should be excerpted" in response.text


def test_home_page_lists_newest_first_without_query(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(episodes_dir / "1.json", 1, title="Older", startDate="2025-01-01T00:00:00Z")
    write_episode(episodes_dir / "2.json", 2, title="Newer", startDate="2026-01-01T00:00:00Z")

    client = TestClient(create_app(tmp_path))
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.index("Newer") < response.text.index("Older")


def test_home_page_uses_relevance_order_when_query_is_present(tmp_path):
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

    client = TestClient(create_app(tmp_path))
    response = client.get("/", params={"q": "alpha beta gamma delta epsilon"})

    assert response.status_code == 200
    assert response.text.index("Alpha") < response.text.index("Neutral")


def test_home_page_searches_non_core_metadata_fields(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "9.json",
        9,
        title="Neutral title",
        description="Neutral description",
        startDate="2026-01-09T00:00:00Z",
        transcriptionAvailable=False,
        guests=["Jane Doe"],
    )

    client = TestClient(create_app(tmp_path))
    response = client.get("/", params={"q": "jane"})

    assert response.status_code == 200
    assert "Neutral title" in response.text


def test_detail_page_renders_transcript_text(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "7.json",
        7,
        title="Transcript Episode",
        description="metadata",
        transcriptionAvailable=True,
    )
    transcript_text = "1\n00:00:00,000 --> 00:00:01,000\nTranscript body\n"
    (transcripts_dir / "7.srt").write_text(transcript_text, encoding="utf-8")

    client = TestClient(create_app(tmp_path))
    response = client.get("/episodes/7")

    assert response.status_code == 200
    assert "1:00:00" in response.text
    assert "Transcript available" in response.text
    assert "Transcript body" in response.text


def test_detail_page_returns_404_for_unknown_episode(tmp_path):
    (tmp_path / "episodes").mkdir()
    (tmp_path / "transcripts").mkdir()

    client = TestClient(create_app(tmp_path))
    response = client.get("/episodes/999")

    assert response.status_code == 404


def test_detail_page_shows_absent_transcript_state_and_raw_metadata(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "8.json",
        8,
        title="No Transcript Episode",
        description="metadata",
        duration=4200,
        transcriptionAvailable=False,
        guests=["Jane Doe"],
    )

    client = TestClient(create_app(tmp_path))
    response = client.get("/episodes/8")

    assert response.status_code == 200
    assert "No transcript text available." in response.text
    assert "Transcript unavailable" in response.text
    assert "guests" in response.text


def test_detail_page_renders_description_html_in_metadata(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "13.json",
        13,
        title="Metadata HTML Episode",
        description=(
            '<p>Clean metadata text.</p>'
            '<p>See <a href="https://example.com/info">example.com/info</a></p>'
        ),
    )

    client = TestClient(create_app(tmp_path))
    response = client.get("/episodes/13")

    assert response.status_code == 200
    assert "Clean metadata text." in response.text
    assert "example.com/info" in response.text
    assert 'href="https://example.com/info"' in response.text
    assert "&lt;p&gt;Clean metadata text." not in response.text


def test_home_page_renders_description_html(tmp_path):
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    write_episode(
        episodes_dir / "12.json",
        12,
        title="HTML Description Episode",
        description=(
            '<p>Robert and Jamie conclude the story.</p>'
            '<p><a href="https://example.com">https://example.com</a></p>'
            '<p>See <a href="https://omnystudio.com/listener">omnystudio.com/listener</a> '
            "for privacy information.</p>"
        ),
    )

    client = TestClient(create_app(tmp_path))
    response = client.get("/")

    assert response.status_code == 200
    assert "Robert and Jamie conclude the story." in response.text
    assert 'href="https://example.com"' in response.text
    assert 'href="https://omnystudio.com/listener"' in response.text
    assert "&lt;p&gt;" not in response.text
