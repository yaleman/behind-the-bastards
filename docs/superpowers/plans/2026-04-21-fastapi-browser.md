# Behind the Bastards FastAPI Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight FastAPI application that browses the archived episode dataset newest-first and searches episode metadata plus transcript text from an in-memory startup snapshot.

**Architecture:** Use a small `btb_browser` package with two focused modules: `data.py` for archive loading, normalization, search, and pagination, and `web.py` for FastAPI routes and template rendering. Keep the UI server-rendered with Jinja templates and minimal CSS, and reuse the existing `episodes/` and `transcripts/` directories without introducing a database or background indexing.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 templates, Uvicorn, standard-library filesystem parsing, `unittest`

---

## File Structure

- Create: `btb_browser/__init__.py`
- Create: `btb_browser/data.py`
- Create: `btb_browser/web.py`
- Create: `templates/index.html`
- Create: `templates/detail.html`
- Create: `static/style.css`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Create: `tests/test_browser_data.py`
- Create: `tests/test_browser_web.py`

### Task 1: Build the In-Memory Archive Loader and Search Logic

**Files:**
- Create: `btb_browser/__init__.py`
- Create: `btb_browser/data.py`
- Create: `tests/test_browser_data.py`

- [ ] **Step 1: Write the failing data/search tests**

Create `tests/test_browser_data.py` with:

```python
import json
import tempfile
import unittest
from pathlib import Path

from btb_browser.data import load_archive, paginate_results, search_records


def write_episode(path: Path, episode_id: int, **overrides):
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


class LoadArchiveTests(unittest.TestCase):
    def test_load_archive_merges_episode_and_transcript_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
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

            self.assertEqual(1, len(records))
            self.assertEqual(2, records[0].id)
            self.assertEqual("Title Match", records[0].title)
            self.assertIn("Transcript body", records[0].transcript_text)
            self.assertIn("interesting metadata", records[0].search_text)

    def test_load_archive_sorts_newest_first_and_handles_missing_transcript(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
            episodes_dir.mkdir()
            transcripts_dir.mkdir()

            write_episode(episodes_dir / "1.json", 1, startDate="2025-01-01T00:00:00Z")
            write_episode(episodes_dir / "2.json", 2, startDate="2026-01-01T00:00:00Z")

            records = load_archive(episodes_dir, transcripts_dir)

            self.assertEqual([2, 1], [record.id for record in records])
            self.assertEqual("", records[0].transcript_text)


class SearchRecordsTests(unittest.TestCase):
    def test_search_records_requires_all_query_terms(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
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

            self.assertEqual([10], [record.id for record in results])

    def test_search_records_prefers_title_match_over_transcript_only_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
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

            self.assertEqual([20, 21], [record.id for record in results])


class PaginationTests(unittest.TestCase):
    def test_paginate_results_returns_page_slice_and_page_count(self):
        items = list(range(1, 121))

        page_items, total_pages = paginate_results(items, page=2, page_size=50)

        self.assertEqual(list(range(51, 101)), page_items)
        self.assertEqual(3, total_pages)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the data/search tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_browser_data -v
```

Expected:
- test discovery starts
- import fails with `ModuleNotFoundError: No module named 'btb_browser'`

- [ ] **Step 3: Write the minimal data/search implementation**

Create `btb_browser/__init__.py` with:

```python
"""Behind the Bastards browser package."""
```

Create `btb_browser/data.py` with:

```python
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


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
    raw_episode: dict[str, Any]
    search_text: str
    score: int = 0


def collect_search_parts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(collect_search_parts(item))
        return parts
    if isinstance(value, dict):
        parts = []
        for item in value.values():
            parts.extend(collect_search_parts(item))
        return parts
    return []


def build_search_text(raw_episode: dict[str, Any], transcript_text: str) -> str:
    parts = collect_search_parts(raw_episode)
    if transcript_text:
        parts.append(transcript_text)
    return " ".join(parts).lower()


def normalize_episode(raw_episode: dict[str, Any], transcript_text: str) -> EpisodeRecord:
    return EpisodeRecord(
        id=int(raw_episode["id"]),
        title=raw_episode.get("title", ""),
        description=raw_episode.get("description", ""),
        start_date=raw_episode.get("startDate", ""),
        duration=raw_episode.get("duration"),
        image_url=raw_episode.get("imageUrl", ""),
        podcast_slug=raw_episode.get("podcastSlug", ""),
        transcription_available=bool(raw_episode.get("transcriptionAvailable")),
        transcript_text=transcript_text,
        raw_episode=raw_episode,
        search_text=build_search_text(raw_episode, transcript_text),
    )


def sort_key(record: EpisodeRecord) -> tuple[str, int]:
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
        transcript_path = transcripts_dir / f"{episode_path.stem}.srt"
        transcript_text = ""
        if transcript_path.exists():
            transcript_text = transcript_path.read_text(encoding="utf-8")
        records.append(normalize_episode(raw_episode, transcript_text))

    records.sort(key=sort_key, reverse=True)
    return records


def score_record(record: EpisodeRecord, terms: list[str]) -> int:
    title = record.title.lower()
    description = record.description.lower()
    transcript = record.transcript_text.lower()
    other_text = record.search_text
    score = 0

    for term in terms:
        if term in title:
            score += 10
        if term in description:
            score += 5
        if term in transcript:
            score += 3
        if term in other_text:
            score += 1

    return score


def search_records(records: Iterable[EpisodeRecord], query: str) -> list[EpisodeRecord]:
    terms = [term.lower() for term in query.split() if term.strip()]
    if not terms:
        return list(records)

    matched: list[EpisodeRecord] = []
    for record in records:
        if all(term in record.search_text for term in terms):
            matched.append(
                EpisodeRecord(
                    id=record.id,
                    title=record.title,
                    description=record.description,
                    start_date=record.start_date,
                    duration=record.duration,
                    image_url=record.image_url,
                    podcast_slug=record.podcast_slug,
                    transcription_available=record.transcription_available,
                    transcript_text=record.transcript_text,
                    raw_episode=record.raw_episode,
                    search_text=record.search_text,
                    score=score_record(record, terms),
                )
            )

    matched.sort(key=lambda record: (record.score, record.start_date, record.id), reverse=True)
    return matched


def paginate_results(items: list[Any], page: int, page_size: int) -> tuple[list[Any], int]:
    safe_page = max(page, 1)
    total_pages = max(math.ceil(len(items) / page_size), 1)
    start = (safe_page - 1) * page_size
    end = start + page_size
    return items[start:end], total_pages
```

- [ ] **Step 4: Run the data/search tests to verify they pass**

Run:

```bash
uv run python -m unittest tests.test_browser_data -v
```

Expected:
- 5 tests run
- all tests pass

- [ ] **Step 5: Commit the data/search layer**

```bash
git add btb_browser/__init__.py btb_browser/data.py tests/test_browser_data.py
git commit -m "feat: add archive browser data layer"
```

### Task 2: Add the FastAPI Routes, Templates, and Styling

**Files:**
- Modify: `pyproject.toml`
- Create: `btb_browser/web.py`
- Create: `templates/index.html`
- Create: `templates/detail.html`
- Create: `static/style.css`
- Create: `tests/test_browser_web.py`

- [ ] **Step 1: Add the web dependencies**

Run:

```bash
uv add fastapi uvicorn jinja2
```

Expected:
- `pyproject.toml` gains `fastapi`, `uvicorn`, and `jinja2`
- `uv.lock` updates

- [ ] **Step 2: Write the failing route tests**

Create `tests/test_browser_web.py` with:

```python
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from btb_browser.web import create_app


def write_episode(path: Path, episode_id: int, **overrides):
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
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")


class WebAppTests(unittest.TestCase):
    def test_homepage_lists_newest_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
            episodes_dir.mkdir()
            transcripts_dir.mkdir()

            write_episode(episodes_dir / "1.json", 1, title="Older", startDate="2025-01-01T00:00:00Z")
            write_episode(episodes_dir / "2.json", 2, title="Newer", startDate="2026-01-01T00:00:00Z")

            client = TestClient(create_app(episodes_dir=episodes_dir, transcripts_dir=transcripts_dir))
            response = client.get("/")

            self.assertEqual(200, response.status_code)
            self.assertLess(response.text.index("Newer"), response.text.index("Older"))

    def test_search_matches_transcript_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
            episodes_dir.mkdir()
            transcripts_dir.mkdir()

            write_episode(
                episodes_dir / "10.json",
                10,
                title="Coup Planning",
                description="Politics episode",
                transcriptionAvailable=True,
            )
            (transcripts_dir / "10.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nBanana republic history\n",
                encoding="utf-8",
            )

            client = TestClient(create_app(episodes_dir=episodes_dir, transcripts_dir=transcripts_dir))
            response = client.get("/", params={"q": "coup banana"})

            self.assertEqual(200, response.status_code)
            self.assertIn("Coup Planning", response.text)
            self.assertIn("1 result", response.text)

    def test_detail_page_shows_transcript(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
            episodes_dir.mkdir()
            transcripts_dir.mkdir()

            write_episode(episodes_dir / "3.json", 3, title="Detail Title", transcriptionAvailable=True)
            (transcripts_dir / "3.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nDetail transcript\n",
                encoding="utf-8",
            )

            client = TestClient(create_app(episodes_dir=episodes_dir, transcripts_dir=transcripts_dir))
            response = client.get("/episodes/3")

            self.assertEqual(200, response.status_code)
            self.assertIn("Detail Title", response.text)
            self.assertIn("Detail transcript", response.text)

    def test_detail_page_returns_404_for_unknown_episode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            episodes_dir = base / "episodes"
            transcripts_dir = base / "transcripts"
            episodes_dir.mkdir()
            transcripts_dir.mkdir()

            client = TestClient(create_app(episodes_dir=episodes_dir, transcripts_dir=transcripts_dir))
            response = client.get("/episodes/999")

            self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the route tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_browser_web -v
```

Expected:
- import succeeds through `fastapi`
- tests fail with `ModuleNotFoundError: No module named 'btb_browser.web'`

- [ ] **Step 4: Write the FastAPI app and templates**

Create `btb_browser/web.py` with:

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from btb_browser.data import EpisodeRecord, load_archive, paginate_results, search_records

PAGE_SIZE = 50


def create_templates() -> Jinja2Templates:
    return Jinja2Templates(directory="templates")


def create_app(
    episodes_dir: Path = Path("episodes"),
    transcripts_dir: Path = Path("transcripts"),
) -> FastAPI:
    app = FastAPI(title="Behind the Bastards Browser")
    templates = create_templates()

    @lru_cache(maxsize=1)
    def get_records() -> list[EpisodeRecord]:
        return load_archive(episodes_dir=episodes_dir, transcripts_dir=transcripts_dir)

    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, q: str = Query(default=""), page: int = Query(default=1, ge=1)):
        records = get_records()
        results = search_records(records, q) if q.strip() else records
        page_items, total_pages = paginate_results(results, page=page, page_size=PAGE_SIZE)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "records": page_items,
                "query": q,
                "page": page,
                "page_size": PAGE_SIZE,
                "total_pages": total_pages,
                "total_results": len(results),
            },
        )

    @app.get("/episodes/{episode_id}", response_class=HTMLResponse)
    def episode_detail(request: Request, episode_id: int):
        records = get_records()
        for record in records:
            if record.id == episode_id:
                return templates.TemplateResponse(
                    request,
                    "detail.html",
                    {
                        "record": record,
                        "metadata": sorted(record.raw_episode.items()),
                    },
                )
        raise HTTPException(status_code=404, detail="Episode not found")

    return app


app = create_app()
```

Create `templates/index.html` with:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Behind the Bastards Browser</title>
    <link rel="stylesheet" href="{{ url_for('static', path='/style.css') }}">
  </head>
  <body>
    <main class="page">
      <header class="hero">
        <h1>Behind the Bastards</h1>
        <form action="/" method="get" class="search-form">
          <input
            type="search"
            name="q"
            value="{{ query }}"
            placeholder="Search titles, descriptions, transcripts, and metadata"
          >
          <button type="submit">Search</button>
        </form>
        <p class="result-count">
          {% if query %}
          {{ total_results }} result{% if total_results != 1 %}s{% endif %} for "{{ query }}"
          {% else %}
          {{ total_results }} episodes
          {% endif %}
        </p>
      </header>

      {% if records %}
      <section class="results">
        {% for record in records %}
        <article class="card">
          <div class="card-meta">
            <span>{{ record.start_date[:10] if record.start_date else "Unknown date" }}</span>
            {% if record.duration %}
            <span>{{ record.duration // 60 }} min</span>
            {% endif %}
            {% if record.transcript_text %}
            <span>Transcript</span>
            {% endif %}
          </div>
          <h2><a href="/episodes/{{ record.id }}">{{ record.title or "Untitled episode" }}</a></h2>
          <p>{{ record.description[:280] }}{% if record.description|length > 280 %}...{% endif %}</p>
        </article>
        {% endfor %}
      </section>
      {% else %}
      <section class="empty-state">
        <p>No episodes matched.</p>
      </section>
      {% endif %}

      <nav class="pagination">
        {% if page > 1 %}
        <a href="/?q={{ query }}&page={{ page - 1 }}">Newer page</a>
        {% endif %}
        <span>Page {{ page }} of {{ total_pages }}</span>
        {% if page < total_pages %}
        <a href="/?q={{ query }}&page={{ page + 1 }}">Older page</a>
        {% endif %}
      </nav>
    </main>
  </body>
</html>
```

Create `templates/detail.html` with:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ record.title }}</title>
    <link rel="stylesheet" href="{{ url_for('static', path='/style.css') }}">
  </head>
  <body>
    <main class="page detail-page">
      <p><a href="/">Back to search</a></p>
      <header class="hero">
        <h1>{{ record.title }}</h1>
        <div class="card-meta">
          <span>{{ record.start_date[:10] if record.start_date else "Unknown date" }}</span>
          {% if record.duration %}
          <span>{{ record.duration // 60 }} min</span>
          {% endif %}
          <span>{% if record.transcript_text %}Transcript available{% else %}No transcript{% endif %}</span>
        </div>
      </header>

      {% if record.description %}
      <section class="panel">
        <h2>Description</h2>
        <p>{{ record.description }}</p>
      </section>
      {% endif %}

      <section class="panel">
        <h2>Transcript</h2>
        {% if record.transcript_text %}
        <pre class="transcript">{{ record.transcript_text }}</pre>
        {% else %}
        <p>No transcript file is available for this episode.</p>
        {% endif %}
      </section>

      <section class="panel">
        <h2>Metadata</h2>
        <dl class="metadata">
          {% for key, value in metadata %}
          <dt>{{ key }}</dt>
          <dd>{{ value }}</dd>
          {% endfor %}
        </dl>
      </section>
    </main>
  </body>
</html>
```

Create `static/style.css` with:

```css
:root {
  --bg: #f7f1e3;
  --panel: #fffdf7;
  --ink: #1c1917;
  --muted: #57534e;
  --line: #d6d3d1;
  --accent: #b45309;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: radial-gradient(circle at top, #fff7ed, var(--bg) 45%);
  color: var(--ink);
  font-family: Georgia, "Times New Roman", serif;
}

.page {
  width: min(960px, calc(100% - 2rem));
  margin: 0 auto;
  padding: 1.5rem 0 3rem;
}

.hero {
  margin-bottom: 1.5rem;
}

h1,
h2 {
  line-height: 1.1;
  margin: 0 0 0.75rem;
}

.search-form {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.75rem;
  margin: 1rem 0 0.75rem;
}

.search-form input,
.search-form button {
  font: inherit;
  padding: 0.8rem 0.9rem;
  border: 1px solid var(--line);
  border-radius: 0.6rem;
}

.search-form button {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.result-count,
.card-meta,
.pagination {
  color: var(--muted);
}

.results,
.panel {
  display: grid;
  gap: 1rem;
}

.card,
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 0.9rem;
  padding: 1rem;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.95rem;
  margin-bottom: 0.5rem;
}

.card a,
.pagination a {
  color: inherit;
}

.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1.5rem;
}

.metadata {
  display: grid;
  grid-template-columns: minmax(140px, 220px) 1fr;
  gap: 0.5rem 1rem;
  margin: 0;
}

.metadata dt {
  font-weight: 700;
}

.metadata dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.transcript {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
}

@media (max-width: 700px) {
  .search-form {
    grid-template-columns: 1fr;
  }

  .pagination,
  .metadata {
    grid-template-columns: 1fr;
  }

  .pagination {
    gap: 0.75rem;
    align-items: flex-start;
  }
}
```

- [ ] **Step 5: Run the route tests to verify they pass**

Run:

```bash
uv run python -m unittest tests.test_browser_web -v
```

Expected:
- 4 tests run
- all tests pass

- [ ] **Step 6: Run the combined test suite**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected:
- `test_archive_btb`, `test_browser_data`, and `test_browser_web` all run
- all tests pass

- [ ] **Step 7: Commit the web app**

```bash
git add pyproject.toml uv.lock btb_browser/web.py templates/index.html templates/detail.html static/style.css tests/test_browser_web.py
git commit -m "feat: add fastapi archive browser"
```

### Task 3: Document and Manually Verify the Browser

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README with browser usage**

Append this section to `README.md`:

```markdown
## Browser UI

Start the local browser app with:

```bash
uv run uvicorn btb_browser.web:app --reload
```

Then open <http://127.0.0.1:8000>.

Behavior:
- the homepage loads the archive into memory once at startup
- browse order is newest-first when no search query is present
- search matches episode metadata, raw archived JSON string values, and transcript text
- search results switch to relevance ordering when `q` is present
- episode detail pages show the full transcript when a `.srt` file exists
```

- [ ] **Step 2: Run the full automated verification again**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected:
- all tests pass

- [ ] **Step 3: Start the app for manual verification**

Run:

```bash
uv run uvicorn btb_browser.web:app --reload
```

Expected:
- Uvicorn starts on `http://127.0.0.1:8000`
- no traceback during startup while reading `episodes/` and `transcripts/`

- [ ] **Step 4: Verify the homepage and search manually**

In a browser:
- load `http://127.0.0.1:8000/`
- confirm the first page shows episodes and the newest items appear first
- search for `phil spector`
- confirm results render and are relevance-ordered
- search for `banana republic`
- confirm transcript-backed matches appear

- [ ] **Step 5: Verify an episode detail page manually**

In a browser:
- open `http://127.0.0.1:8000/episodes/329558837`
- confirm the page shows the episode title, description, metadata, and transcript text

- [ ] **Step 6: Commit the README update**

```bash
git add README.md
git commit -m "docs: add browser usage instructions"
```
