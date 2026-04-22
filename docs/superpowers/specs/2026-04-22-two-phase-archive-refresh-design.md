# Behind the Bastards Two-Phase Archive Refresh Design

## Summary

Change the archive refresh job in `scripts/archive_btb.py` from a single serial loop into a two-phase process.

Phase 1 remains serial and pages through the iHeart episode API, writing raw episode JSON files to `episodes/` and building a transcript work list from the fetched metadata.

Phase 2 processes transcript-capable episodes with a bounded worker pool so transcript HTML discovery and transcript downloads can run concurrently. The archive command stays `uv run python scripts/archive_btb.py`, and failure handling remains best-effort per transcript instead of aborting the whole run.

## Goals

- Reduce total dataset refresh time by parallelising transcript work.
- Keep episode metadata refresh behaviour unchanged.
- Keep the existing archive command and `mise` task stable.
- Preserve the current on-disk output layout in `episodes/` and `transcripts/`.
- Keep transcript failures isolated to individual episodes.

## Non-Goals

- No new long-lived service or queue.
- No change to transcript file format.
- No separate operator workflow for “metadata only” versus “transcripts only”.
- No attempt to avoid transcript refreshes for unchanged episodes in the default path.
- No backwards-compatibility layer for alternative archive pipelines that do not exist in this repo.

## Current Problem

Today `scripts/archive_btb.py` fetches episode metadata and transcript content in the same loop:

1. fetch one page of episode metadata
2. write one episode JSON file
3. if `transcriptionAvailable` is true:
4. fetch the episode detail page
5. extract the Omny transcript URL
6. fetch the transcript
7. write the compressed transcript file

That makes the entire refresh effectively serialized around transcript network latency. Metadata pagination is inherently serial because the next page key depends on the prior response, but transcript work is independent once the episode list is known.

## Proposed Architecture

### Phase 1: Metadata Refresh

The metadata phase keeps the current page-by-page API traversal:

- fetch episode pages in order
- write each raw episode payload to `episodes/<episode_id>.json`
- record the episode write status in the run counters
- append transcript-capable episodes to a transcript job list

This phase owns only metadata writes and transcript job discovery.

### Phase 2: Parallel Transcript Refresh

After all episode metadata has been collected, a transcript phase runs a bounded thread pool over the transcript job list.

Each transcript worker:

1. fetches the episode page HTML
2. extracts the Omny transcript URL
3. fetches the transcript text
4. writes `transcripts/<episode_id>.srt.zst` only if content changed
5. returns a structured result describing `new`, `updated`, `unchanged`, `missing`, or `failed`

The main thread consumes completed worker results and updates counters, warnings, and progress output.

## Concurrency Model

Use `concurrent.futures.ThreadPoolExecutor` with a bounded default worker count.

Why threads:

- the workload is network-bound
- the existing script uses blocking `urllib.request`
- this change stays small and direct without moving the script to `asyncio`

The default worker count should be aggressive enough to materially reduce runtime without being unbounded. A constant default of `16` workers is acceptable for this repo. The implementation may allow overriding that value through a CLI flag later, but that is not required for the first cut.

## Responsibilities and Boundaries

Keep the refresh code split by purpose:

- metadata helpers page and persist episode JSON
- transcript helpers fetch and persist transcript content for one episode
- the archive orchestration coordinates the two phases and reporting

The existing `archive_episode()` function currently mixes those concerns. The redesign should replace it with smaller helpers rather than layering concurrency on top of the combined function.

## Logging and Reporting

The archive command should still print useful progress and a final summary.

Required reporting behaviour:

- metadata phase prints page fetch progress
- metadata phase prints per-episode metadata write status
- transcript phase prints per-episode transcript status as workers finish
- final summary includes the same counter categories already present today

Result ordering for transcript logs does not need to match episode order; completion order is acceptable.

## Error Handling

Per-episode transcript failures remain non-fatal.

Rules:

- if an episode says transcripts are unavailable, count it as `transcripts_missing`
- if the episode page lacks a transcript link, count it as `transcripts_missing` and warn
- if transcript fetching or writing raises an exception, count it as `transcripts_failed` and warn
- metadata failures should still fail the run because the archive cannot continue without the paged API responses

## Command Surface

Keep these stable:

- `uv run python scripts/archive_btb.py`
- `mise run update-dataset`
- `.github/workflows/update-dataset.yml`

The operational change is internal to `scripts/archive_btb.py`.

## Testing Strategy

Add or update tests in `tests/test_archive_btb.py` to cover:

- serial metadata collection producing transcript jobs
- transcript worker success with transcript write status propagation
- transcript worker missing-link behaviour
- transcript worker exception handling
- two-phase archive orchestration aggregating counters correctly across metadata and transcript phases

Tests should use fake fetch functions and small temporary directories. They should not perform real network I/O.

## Acceptance Criteria

The change is complete when:

- `scripts/archive_btb.py` performs metadata refresh before transcript refresh
- transcript refresh runs concurrently with a bounded worker pool
- the existing archive entrypoint stays unchanged
- the final summary counters still reflect episode and transcript outcomes accurately
- transcript failures still do not abort the run
- the repo test suite covering archive behaviour passes

## Assumptions

- Transcript HTML discovery and transcript downloads are independent per episode once metadata collection is complete.
- Concurrent transcript writes are safe because each worker writes a distinct transcript path.
- The current archive dataset size is small enough that holding the transcript job list in memory for one run is acceptable.
