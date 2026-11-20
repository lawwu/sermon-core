"""Group timestamped segments into readable paragraphs.

Whisper output is a wall of ~5-second lines. Readers need paragraphs;
deep links need a timestamp per paragraph. Rules (no LLM, so the whole
archive reprocesses in seconds and costs nothing):

- a long silence between segments starts a new paragraph
- once a paragraph is "full" (time or length), break at the next
  sentence boundary
- hard caps guarantee a break even in run-on speech
"""

from __future__ import annotations

from dataclasses import dataclass

from .parse import Segment

GAP_HARD = 4.0        # silence this long always starts a new paragraph
GAP_SOFT = 2.0        # this long starts one if the previous sentence ended
TARGET_SECONDS = 65.0  # prefer breaking after this much speech...
TARGET_CHARS = 700     # ...or this much text, at a sentence boundary
HARD_SECONDS = 150.0   # never let a paragraph exceed these
HARD_CHARS = 1400

_SENTENCE_END = (".", "!", "?", '."', '!"', '?"', ".'", "!'", "?'", ".)", "?)", "!)")


@dataclass
class Paragraph:
    start: float
    end: float
    text: str


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith(_SENTENCE_END)


def group_paragraphs(segments: list[Segment]) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    current: list[Segment] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(seg.text for seg in current).strip()
        if text:
            paragraphs.append(
                Paragraph(start=current[0].start, end=current[-1].end, text=text)
            )
        current.clear()

    for seg in segments:
        if current:
            gap = seg.start - current[-1].end
            elapsed = current[-1].end - current[0].start
            chars = sum(len(s.text) + 1 for s in current)
            prev_done = _ends_sentence(current[-1].text)
            if (
                gap >= GAP_HARD
                or (gap >= GAP_SOFT and prev_done)
                or ((elapsed >= TARGET_SECONDS or chars >= TARGET_CHARS) and prev_done)
                or elapsed >= HARD_SECONDS
                or chars >= HARD_CHARS
            ):
                flush()
        current.append(seg)
    flush()
    return paragraphs
