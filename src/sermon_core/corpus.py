"""Load a church's recordings: metadata cache + transcripts -> Sermons."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .model import Sermon
from .paragraphs import group_paragraphs
from .parse import parse_file
from .scripture import extract_references
from .source import Source


@dataclass
class Corpus:
    sermons: list[Sermon]  # oldest first, ties by id
    skipped: list[str] = field(default_factory=list)  # "<id>: <reason>"


def load(source: Source, limit: int | None = None) -> Corpus:
    """Every recording with a usable transcript and an upload date.

    Title references are parsed into `Sermon.references`. Recordings without a
    transcript, an upload date, or any paragraphs land in `skipped` with the
    reason. `limit` keeps the first N in metadata order (for quick builds).
    """
    metadata = json.loads(source.metadata_path.read_text(encoding="utf-8"))
    sermons: list[Sermon] = []
    skipped: list[str] = []
    for video_id, info in metadata.items():
        transcript_path = source.transcripts_dir / f"{video_id}.txt"
        upload_date = str(info.get("upload_date") or "")
        if not transcript_path.exists():
            skipped.append(f"{video_id}: no transcript")
            continue
        if len(upload_date) != 8:
            skipped.append(f"{video_id}: no upload date")
            continue
        paragraphs = group_paragraphs(parse_file(transcript_path))
        if not paragraphs:
            skipped.append(f"{video_id}: empty transcript")
            continue
        title = info.get("title") or video_id
        sermons.append(
            Sermon(
                id=video_id,
                title=title,
                upload_date=upload_date,
                duration=info.get("duration"),
                url=info.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                thumbnail=info.get("thumbnail"),
                paragraphs=paragraphs,
                references=extract_references(title),
            )
        )
        if limit and len(sermons) >= limit:
            break
    sermons.sort(key=lambda s: (s.upload_date, s.id))
    return Corpus(sermons, skipped)
