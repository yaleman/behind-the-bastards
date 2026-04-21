from __future__ import annotations

from pathlib import Path

from btb_browser.transcripts import (
    read_transcript_text,
    transcript_storage_path,
    write_transcript_text_if_changed,
)


def migrate_transcripts(transcripts_dir: Path = Path("transcripts")) -> dict[str, int]:
    counters = {
        "transcripts_new": 0,
        "transcripts_updated": 0,
        "transcripts_unchanged": 0,
    }
    if not transcripts_dir.exists():
        return counters

    for legacy_path in sorted(transcripts_dir.glob("*.srt")):
        episode_id = legacy_path.stem
        transcript_text = legacy_path.read_text(encoding="utf-8")
        target_path = transcript_storage_path(transcripts_dir, episode_id)
        status = write_transcript_text_if_changed(target_path, transcript_text)
        counters[f"transcripts_{status}"] += 1

        if read_transcript_text(transcripts_dir, episode_id) == transcript_text:
            legacy_path.unlink()

    return counters


def main() -> int:
    summary = migrate_transcripts()
    print("Summary:")
    for key, value in summary.items():
        print(f"  {key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
