"""Conservative, church-configured message series classification.

Study dates apply only to titles identifying a Bible study. Upload weekdays
are never treated as service dates. Ambiguous messages remain unassigned.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .model import Sermon


@dataclass
class MessageSeries:
    slug: str
    title: str
    category: str
    description: str = ""
    current: bool = False
    sermons: list[Sermon] = field(default_factory=list)


def group_series(sermons: list[Sermon], rules: list[dict]) -> list[MessageSeries]:
    groups = [MessageSeries(**{k: v for k, v in rule.items()
                              if k in {"slug", "title", "category", "description", "current"}})
              for rule in rules]
    overrides = {video_id: group for rule, group in zip(rules, groups)
                 for video_id in rule.get("include_ids", [])}
    for sermon in sermons:
        if sermon.id in overrides:
            overrides[sermon.id].sermons.append(sermon)
            continue
        for rule, group in zip(rules, groups):
            if rule.get("start", "00000000") > sermon.upload_date or sermon.upload_date > rule.get("end", "99999999"):
                continue
            if rule.get("exclude") and re.search(rule["exclude"], sermon.title, re.I):
                continue
            if rule.get("pattern") and not re.search(rule["pattern"], sermon.title, re.I):
                continue
            if book := rule.get("book"):
                title_books = {r.book for r in sermon.references}
                if title_books:
                    if title_books != {book}:
                        continue
                else:
                    # Require an explicit passage introduction, not an incidental
                    # reference or an assumption about the date of the series.
                    text = " ".join(p.text for p in sermon.paragraphs)
                    introductions = re.findall(
                        r"(?:turn|open) (?:with me )?(?:(?:your|our) bibles? )?"
                        r"(?:with me )?(?:over )?to\s+(?:the (?:book|gospel) of )?"
                        r"([123]?\s*[A-Za-z]+)\s+(?:chapter\b|\d+)",
                        text, re.I,
                    )
                    # Standalone sermon recordings often start directly with
                    # the passage, without "turn your Bibles". Restrict this
                    # evidence to the opening, followed by a reading cue.
                    opening = re.search(
                        r"\b(Luke|Romans|Hebrews)\s+(?:chapter\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
                        r"[^.!?]{0,160}(?:read|verse)", text[:1500], re.I,
                    )
                    if opening:
                        introductions = [opening.group(1)]
                    counts = Counter(b.strip().lower() for b in introductions)
                    if not counts or counts.most_common(1)[0][0] != book.lower():
                        continue
                    if len(counts) > 1 and counts.most_common(2)[0][1] == counts.most_common(2)[1][1]:
                        continue
            group.sermons.append(sermon)
            break
    for group in groups:
        group.sermons.sort(key=lambda s: (s.upload_date, s.id))
    return groups
