# Behind the Bastards Archive

This repo contains a direct Python scraper for archiving the Behind the Bastards podcast episode catalog from iHeart.

The script:
- pages through the podcast API until it has the full episode list
- writes each raw episode payload to `episodes/<episode_id>.json` in a serial metadata pass
- refreshes available transcripts in a separate parallel pass and writes them to `transcripts/<episode_id>.srt.zst`
- refreshes files only when the upstream content changes

## Usage

Run the archive job with:

```bash
uv run python scripts/archive_btb.py
```

Or via `mise`:

```bash
mise run update-dataset
```

## Container

Build the app container with:

```bash
docker build -t behind-the-bastards .
```

Run it with:

```bash
docker run --rm -p 8000:8000 behind-the-bastards
```

The image includes the archived `episodes/` and `transcripts/` directories, so the browser UI is ready to serve immediately.

## Browser UI

Start the local browser app with:

```bash
uv run behind-the-bastards --debug
```

Then open <http://127.0.0.1:8000>.

The browser command accepts:
- `--host` to change the bind address
- `--port` to change the listen port
- `--debug` to enable Uvicorn reload mode with debug logging

Install the WebKit browser runtime once before running the browser smoke tests:

```bash
uv run playwright install webkit
```

Behavior:
- the homepage loads the archive into memory once at startup
- browse order is newest-first when no search query is present
- search matches episode metadata, raw archived JSON string values, and transcript text
- search results switch to relevance ordering when `q` is present
- episode detail pages show the full transcript when a `.srt.zst` file exists

Run the full test suite, including the WebKit smoke tests, with:

```bash
uv run pytest
```

Migrate existing transcript files with:

```bash
uv run python scripts/migrate_transcripts_to_zstd.py
```

## Output Layout

- `scripts/archive_btb.py`: archive entrypoint
- `episodes/`: raw episode API objects, one JSON file per episode ID
- `transcripts/`: transcript files, one zstd-compressed SubRip file per episode ID

## Rerun Behavior

The scraper refreshes in two phases:

- a serial metadata pass that pages the iHeart API and updates `episodes/`
- a bounded parallel transcript pass that refreshes transcript-capable episodes concurrently

Fetched content is still compared with the existing files, and only files whose contents changed are rewritten. Unchanged episode and transcript files are left alone.

## Transcript Caveat

Some episodes report transcript support, but the episode page may still fail to expose a usable transcript link or transcript fetches may fail. In those cases the script keeps the episode JSON file, records the transcript issue in its summary, and continues.

## Container Publishing

Pushes to `main` trigger `.github/workflows/publish-container.yml`, which uses Docker's maintained reusable workflow from [`docker/github-builder`](https://github.com/docker/github-builder) to build and publish a multi-arch image for `linux/amd64` and `linux/arm64` to GHCR as:

- `ghcr.io/<owner>/<repo>:latest`
- `ghcr.io/<owner>/<repo>:sha-<short-commit>`

## Scheduled Archive Updates

`.github/workflows/update-dataset.yml` runs every day at `00:00 UTC` and on manual dispatch. It refreshes the archive with `scripts/archive_btb.py` and commits any changed `episodes/` or `transcripts/` files back to `main`.
