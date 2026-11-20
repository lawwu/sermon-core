"""What the core needs to know about a church's recordings.

A structural protocol, not a config format: each app keeps its own YAML schema
and passes any object with these attributes (both apps' ChurchConfig do).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Source(Protocol):
    name: str  # shown in ingest logs
    youtube_channel: str  # channel URL ingest discovers videos from
    metadata_path: Path  # JSON cache: video id -> yt-dlp metadata
    transcripts_dir: Path  # <video id>.txt, whisper-format "[hh:mm:ss.mmm --> ...]   text"
    # Optional whisper.cpp fallback for transcripts Parakeet fails the yield check on.
    # Machine-local; when missing, the recording is kept with engine "low_yield".
    whisper_bin: Path | None
    whisper_model: Path | None
