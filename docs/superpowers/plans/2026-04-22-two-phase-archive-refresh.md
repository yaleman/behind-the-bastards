# Two-Phase Archive Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `scripts/archive_btb.py` into a serial metadata pass and a parallel transcript refresh pass so dataset updates finish substantially faster without changing the existing command surface.

**Architecture:** Keep episode pagination and metadata writes serial because the upstream API is page-key driven. Build a transcript job list during that pass, then process those jobs with a bounded `ThreadPoolExecutor`, returning structured results to the main thread for counters, warnings, and progress output.

**Tech Stack:** Python 3.14, `urllib.request`, `concurrent.futures.ThreadPoolExecutor`, `pytest`, zstd transcript storage helpers

---

## File Map

- Modify: `scripts/archive_btb.py`
  - Split metadata and transcript responsibilities into smaller helpers.
  - Add transcript job/result structures and the bounded parallel transcript phase.
- Modify: `tests/test_archive_btb.py`
  - Replace mixed serial-path tests with coverage for transcript jobs, worker results, and two-phase orchestration.
- Modify: `README.md`
  - Document the two-phase refresh behavior while keeping the same command examples.

### Task 1: Lock the New Orchestration with Tests

**Files:**
- Modify: `tests/test_archive_btb.py`
- Test: `tests/test_archive_btb.py`

- [ ] **Step 1: Write a test for the metadata phase building transcript jobs**

```python
def test_archive_metadata_page_collects_transcript_jobs(tmp_path):
    counters = archive_btb.make_counters()
    jobs = []

    episode_with_transcript = {"id": 1, "transcriptionAvailable": True}
    episode_without_transcript = {"id": 2, "transcriptionAvailable": False}

    archive_btb.archive_metadata_episode(
        episode_with_transcript,
        tmp_path / "episodes",
        counters,
        jobs,
    )
    archive_btb.archive_metadata_episode(
        episode_without_transcript,
        tmp_path / "episodes",
        counters,
        jobs,
    )

    assert [job.episode_id for job in jobs] == [1]
    assert counters["episodes_new"] == 2
    assert counters["transcripts_missing"] == 1
```

- [ ] **Step 2: Run the targeted test to verify it fails before the refactor**

Run: `uv run pytest tests/test_archive_btb.py -k metadata_page_collects_transcript_jobs -v`

Expected: FAIL because `archive_metadata_episode` and transcript job handling do not exist yet.

- [ ] **Step 3: Write a test for transcript worker success**

```python
def test_refresh_transcript_job_returns_new_status(tmp_path):
    job = archive_btb.TranscriptJob(episode_id=329558837)

    def fake_fetch_text(url):
        if url.endswith("/#transcription"):
            return '<a href="https://api.omny.fm/orgs/example/clips/clip-id/transcript?format=SubRip&t=12345">'
        return "1\n00:00:00,000 --> 00:00:01,000\nhello\n"

    result = archive_btb.refresh_transcript_job(
        job=job,
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=fake_fetch_text,
    )

    assert result.episode_id == 329558837
    assert result.status == "new"
    assert result.warning is None
```

- [ ] **Step 4: Write tests for missing-link and failed transcript cases**

```python
def test_refresh_transcript_job_returns_missing_when_link_not_found(tmp_path):
    result = archive_btb.refresh_transcript_job(
        job=archive_btb.TranscriptJob(episode_id=1),
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=lambda url: "<html></html>",
    )

    assert result.status == "missing"
    assert "transcript link not found" in result.warning


def test_refresh_transcript_job_returns_failed_on_exception(tmp_path):
    def fake_fetch_text(url):
        raise RuntimeError("boom")

    result = archive_btb.refresh_transcript_job(
        job=archive_btb.TranscriptJob(episode_id=1),
        transcripts_dir=tmp_path / "transcripts",
        fetch_text=fake_fetch_text,
    )

    assert result.status == "failed"
    assert "boom" in result.warning
```

- [ ] **Step 5: Write a high-level orchestration test**

```python
def test_archive_all_runs_metadata_then_parallel_transcripts(tmp_path):
    pages = [
        {
            "data": [
                {"id": 1, "transcriptionAvailable": True},
                {"id": 2, "transcriptionAvailable": False},
            ],
            "links": {},
        }
    ]

    calls = []

    def fake_fetch_json(url):
        calls.append(("json", url))
        return pages.pop(0)

    def fake_fetch_text(url):
        calls.append(("text", url))
        if url.endswith("/#transcription"):
            return '<a href="https://api.omny.fm/orgs/example/clips/clip-id/transcript?format=SubRip&t=12345">'
        return "1\n00:00:00,000 --> 00:00:01,000\nhello\n"

    counters = archive_btb.archive_all(
        episodes_dir=tmp_path / "episodes",
        transcripts_dir=tmp_path / "transcripts",
        fetch_json=fake_fetch_json,
        fetch_text=fake_fetch_text,
        max_transcript_workers=2,
    )

    assert counters["episodes_new"] == 2
    assert counters["transcripts_new"] == 1
    assert counters["transcripts_missing"] == 1
```

- [ ] **Step 6: Run the archive test file and confirm the new tests fail for the right reasons**

Run: `uv run pytest tests/test_archive_btb.py -v`

Expected: FAIL only on the new two-phase tests because the old implementation is still serial and missing the new helpers.

### Task 2: Refactor `scripts/archive_btb.py` into Two Phases

**Files:**
- Modify: `scripts/archive_btb.py`
- Test: `tests/test_archive_btb.py`

- [ ] **Step 1: Add explicit transcript job and result structures**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptJob:
    episode_id: int


@dataclass(frozen=True)
class TranscriptResult:
    episode_id: int
    status: str
    warning: str | None = None
```

- [ ] **Step 2: Split metadata writing from transcript refreshing**

```python
def archive_metadata_episode(
    episode: dict[str, Any],
    episodes_dir: Path,
    counters: dict[str, int],
    transcript_jobs: list[TranscriptJob],
) -> str:
    episode_id = episode["id"]
    episode_path = episodes_dir / f"{episode_id}.json"
    episode_status = write_text_if_changed(episode_path, serialize_json(episode))
    counters[f"episodes_{episode_status}"] += 1

    if episode.get("transcriptionAvailable"):
        transcript_jobs.append(TranscriptJob(episode_id=episode_id))
    else:
        counters["transcripts_missing"] += 1

    return episode_status
```

- [ ] **Step 3: Add the transcript worker helper**

```python
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
        status = write_transcript_text_if_changed(transcript_path, transcript_text)
        return TranscriptResult(episode_id=job.episode_id, status=status)
    except Exception as exc:
        return TranscriptResult(
            episode_id=job.episode_id,
            status="failed",
            warning=f"episode {job.episode_id}: transcript fetch failed: {exc}",
        )
```

- [ ] **Step 4: Add the bounded parallel transcript phase**

```python
def refresh_transcripts(
    transcript_jobs: list[TranscriptJob],
    transcripts_dir: Path,
    counters: dict[str, int],
    warn: Callable[[str], None],
    fetch_text: Callable[[str], str],
    max_transcript_workers: int,
) -> None:
    with ThreadPoolExecutor(max_workers=max_transcript_workers) as executor:
        futures = [
            executor.submit(
                refresh_transcript_job,
                job,
                transcripts_dir,
                fetch_text,
            )
            for job in transcript_jobs
        ]

        for future in as_completed(futures):
            result = future.result()
            counters[f"transcripts_{result.status}"] += 1
            if result.warning is not None:
                warn(result.warning)
            print(f"Transcript {result.episode_id}: {result.status}")
```

- [ ] **Step 5: Rework `archive_all()` to call metadata first, then transcripts**

```python
def archive_all(..., max_transcript_workers: int = DEFAULT_TRANSCRIPT_WORKERS) -> dict[str, int]:
    counters = make_counters()
    transcript_jobs: list[TranscriptJob] = []

    for index, episode in enumerate(iter_episodes(fetch_page), start=1):
        episode_status = archive_metadata_episode(
            episode=episode,
            episodes_dir=episodes_dir,
            counters=counters,
            transcript_jobs=transcript_jobs,
        )
        print(f"Episode {index}: {episode['id']} (episode={episode_status})")

    refresh_transcripts(
        transcript_jobs=transcript_jobs,
        transcripts_dir=transcripts_dir,
        counters=counters,
        warn=warn,
        fetch_text=fetch_text,
        max_transcript_workers=max_transcript_workers,
    )
```

- [ ] **Step 6: Run the archive tests and verify the refactor passes**

Run: `uv run pytest tests/test_archive_btb.py -v`

Expected: PASS for the full archive test module.

### Task 3: Update Docs and Verify the Repo Checks

**Files:**
- Modify: `README.md`
- Test: `tests/test_archive_btb.py`

- [ ] **Step 1: Update the README to describe the two-phase refresh**

```markdown
The script now refreshes in two phases:
- a serial metadata pass that pages the iHeart API and updates `episodes/`
- a parallel transcript pass that refreshes transcript-capable episodes concurrently
```

- [ ] **Step 2: Run the targeted repo checks**

Run: `uv run pytest -q`

Expected: PASS for the full test suite.

Run: `uv run ty check`

Expected: PASS with no type errors.

- [ ] **Step 3: Review the diff for scope control**

Run: `git diff -- scripts/archive_btb.py tests/test_archive_btb.py README.md docs/superpowers/specs/2026-04-22-two-phase-archive-refresh-design.md docs/superpowers/plans/2026-04-22-two-phase-archive-refresh.md`

Expected: Only the archive refactor, tests, README note, and spec/plan docs are included.

## Self-Review

- Spec coverage: metadata-first orchestration, bounded transcript concurrency, stable command surface, non-fatal transcript failures, and verification are all mapped to tasks above.
- Placeholder scan: no placeholder text or deferred work markers remain in the plan.
- Type consistency: the plan consistently uses `TranscriptJob`, `TranscriptResult`, `archive_metadata_episode()`, `refresh_transcript_job()`, and `refresh_transcripts()`.
