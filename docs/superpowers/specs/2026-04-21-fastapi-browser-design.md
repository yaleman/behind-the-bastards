# Behind the Bastards FastAPI Browser Design

## Summary

Build a lightweight FastAPI application for browsing and searching the archived Behind the Bastards dataset stored in `episodes/` and `transcripts/`.

The first version is intentionally simple:
- server-rendered HTML only
- direct use of the existing archive files
- one in-memory dataset built at startup
- browse newest-first by default
- relevance ordering when a search query is present

This version does not add a database, background indexing, or client-side application framework.

## Goals

- Provide a local web UI to browse the archived podcast episodes.
- Provide fast search across episode metadata and transcript text.
- Keep implementation small and easy to reason about.
- Reuse the existing archive output without changing its file formats.

## Non-Goals

- No authentication or multi-user behavior.
- No API-first frontend architecture.
- No persistent search index or database.
- No editing, tagging, annotation, or re-archiving from the UI.
- No advanced query language beyond plain text search.

## Data Model

At startup, the app scans `episodes/*.json` and `transcripts/*.srt` and builds one in-memory record per episode.

Each in-memory record contains:
- `id`: episode ID from the JSON filename and payload
- `title`
- `description`
- `start_date`
- `duration`
- `image_url`
- `podcast_slug`
- `transcription_available`
- `transcript_text`: transcript body if `transcripts/<id>.srt` exists, otherwise empty string
- `raw_episode`: original parsed episode JSON for display on the detail page
- `search_text`: one normalized lowercase string containing all searchable content

`search_text` is derived from:
- all string values present anywhere in the raw episode JSON object
- the transcript text
- scalar IDs or date-like values converted to strings when useful for matching

This keeps the search contract broad without inventing a schema-specific index.

## Application Behavior

### Startup

On startup the app:
1. reads every episode JSON file from `episodes/`
2. reads the matching transcript file from `transcripts/` when present
3. normalizes each episode into an in-memory record
4. sorts the baseline browse order newest-first using `startDate`, with episode ID as a stable tiebreaker

If the archive directories are missing or empty, the app should still start and render an empty state rather than crash.

### Browse View

`GET /` renders the main page.

Without a query:
- results are ordered newest-first
- page shows a search box and a paginated episode list
- each row shows title, date, duration when available, and a short description excerpt
- each row links to the episode detail page

With a query via `?q=...`:
- results are filtered to episodes whose searchable content contains all query terms
- results are ordered by descending relevance score, then by newest-first for ties
- the page shows the active query and total match count

Pagination is query-string driven using `page` with a fixed page size.

### Search Behavior

Search is case-insensitive plain text matching over:
- episode metadata
- raw episode JSON string values
- transcript text

Query handling:
- split on whitespace into terms
- ignore empty terms
- require every term to appear somewhere in `search_text`

Relevance scoring is intentionally simple:
- title matches get the highest weight
- description matches get a medium weight
- transcript matches get a lower but meaningful weight
- additional matches in other searchable fields contribute minimally

The score only needs to be stable and obviously useful; the first version does not need fuzzy matching, stemming, phrase queries, or typo tolerance.

### Episode Detail View

`GET /episodes/{episode_id}` renders one episode page.

The detail page shows:
- title
- date
- duration
- description
- transcript availability state
- transcript text when present
- a compact metadata section for the raw episode payload

The transcript should be displayed as readable preformatted text, preserving line breaks from the `.srt` file.

If the episode ID does not exist, return a standard 404 page.

## UI Direction

The UI should stay lightweight and readable, not generic admin chrome.

Requirements:
- simple server-rendered layout
- search input prominent near the top
- results optimized for scanning
- no subtitle-heavy layout
- responsive enough for desktop and mobile browsers

The main page should prioritize content density over decorative framing because the archive is large and browsing speed matters more than polish.

## Routing and Structure

Use a small app structure:
- FastAPI app module
- data-loading/search module
- templates for index and detail pages
- minimal static CSS if needed

Keep responsibilities narrow:
- loader code handles filesystem parsing and normalization
- search code handles filtering, scoring, and pagination inputs
- route handlers adapt request parameters to rendered templates

Avoid introducing abstractions beyond what is needed for these boundaries.

## Dependencies

Add only the dependencies needed for the web app:
- `fastapi`
- `uvicorn`
- `jinja2`

Keep all archive-reading logic on the Python standard library.

## Testing Strategy

Add automated tests for:
- loading episode JSON and transcript files into normalized in-memory records
- building broad searchable text from episode payload plus transcript
- default browse ordering newest-first
- query filtering requiring all terms
- relevance ordering preferring title/description matches over transcript-only matches
- episode detail route success and 404 behavior

Use small fixture files created inside tests rather than depending on the full archive.

## Acceptance Criteria

The feature is complete when:
- `uv run` can start a FastAPI app locally against the archived dataset
- the homepage loads without a search query and shows newest-first episodes
- a query can match transcript text and metadata from the same request path
- search results reorder by relevance when a query is present
- an episode detail page shows transcript text when available
- missing transcripts do not break browse or detail pages

## Assumptions

- The archive remains file-based in `episodes/` and `transcripts/`.
- Loading the full archive into memory at startup is acceptable for this dataset size.
- Search quality should be good enough for direct substring matching plus simple weighting.
- The app is primarily for local use, so startup cost is less important than fast interactive requests.
