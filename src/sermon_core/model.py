"""Shared sermon model assembled from metadata + parsed transcript."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .paragraphs import Paragraph
from .scripture import Reference


@dataclass
class Sermon:
    id: str
    title: str
    upload_date: str  # YYYYMMDD
    duration: int | None
    url: str
    thumbnail: str | None
    paragraphs: list[Paragraph]
    references: list[Reference] = field(default_factory=list)

    @property
    def year(self) -> str:
        return self.upload_date[:4]

    @property
    def date_display(self) -> str:
        d = self.upload_date
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

    @property
    def platform(self) -> str:
        return "vimeo" if "vimeo.com" in (self.url or "") else "youtube"

    @property
    def duration_display(self) -> str:
        if not self.duration:
            return ""
        mins, hrs = (self.duration // 60) % 60, self.duration // 3600
        return f"{hrs}h {mins}m" if hrs else f"{mins}m"

    def timestamp_url(self, seconds: float) -> str:
        s = int(seconds)
        if self.platform == "vimeo":
            return f"{self.url}#t={s}s"
        joiner = "&" if "?" in self.url else "?"
        return f"{self.url}{joiner}t={s}"

    @property
    def description(self) -> str:
        """First ~160 chars of the transcript, for meta description."""
        text = self.paragraphs[0].text if self.paragraphs else ""
        text = re.sub(r"\s+", " ", text).strip()
        return text[:157] + "…" if len(text) > 160 else text
