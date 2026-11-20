"""Parse whisper.cpp transcript files into timestamped segments.

Input format (one line per segment):

    [00:12:34.000 --> 00:12:39.000]   For God so loved the world...

Non-speech annotations ([MUSIC], (applause), ♪ ...) are dropped so praise
sets and applause never reach the transcript. Timestamps are preserved —
they power deep links into the video.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SEG_RE = re.compile(
    r"^\[(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> (\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.*)$"
)
# [MUSIC], (applause), [BLANK_AUDIO], ♪ lyrics ♪ ... — annotation-only noise
ANNOTATION_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|♪+[^♪]*♪+|♪+")
MAX_CONSECUTIVE_REPEATS = 2  # whisper sometimes loops a phrase; collapse runs


@dataclass
class Segment:
    start: float
    end: float
    text: str


def _hms_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _clean_text(text: str) -> str:
    text = ANNOTATION_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_lines(lines: Iterable[str]) -> list[Segment]:
    segments: list[Segment] = []
    repeats = 0
    for line in lines:
        match = SEG_RE.match(line.rstrip("\n"))
        if not match:
            # Continuation line without a timestamp: glue onto previous segment
            text = _clean_text(line)
            if text and segments:
                segments[-1].text = f"{segments[-1].text} {text}".strip()
            continue
        start = _hms_to_seconds(*match.group(1, 2, 3, 4))
        end = _hms_to_seconds(*match.group(5, 6, 7, 8))
        text = _clean_text(match.group(9))
        if not text:
            continue
        if segments and text == segments[-1].text:
            repeats += 1
            if repeats >= MAX_CONSECUTIVE_REPEATS:
                segments[-1].end = end
                continue
        else:
            repeats = 0
        segments.append(Segment(start=start, end=end, text=text))
    return segments


def parse_file(path: Path) -> list[Segment]:
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        return parse_lines(fh)
