"""Extract Bible references ("Galatians 3:10-14") from sermon titles/text.

Titles are the high-precision source (churches put the passage in the
title). Series titles ("Galatians (Fall 2023)") name whole books without
chapters; `books_named` finds those. Canonical book order is preserved for
display.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

# (canonical name, [aliases]) in canonical order
_BOOKS: list[tuple[str, list[str]]] = [
    ("Genesis", ["Gen"]),
    ("Exodus", ["Exod", "Ex"]),
    ("Leviticus", ["Lev"]),
    ("Numbers", ["Num"]),
    ("Deuteronomy", ["Deut", "Dt"]),
    ("Joshua", ["Josh"]),
    ("Judges", ["Judg"]),
    ("Ruth", []),
    ("1 Samuel", ["1 Sam", "I Samuel", "First Samuel"]),
    ("2 Samuel", ["2 Sam", "II Samuel", "Second Samuel"]),
    ("1 Kings", ["1 Kgs", "I Kings", "First Kings"]),
    ("2 Kings", ["2 Kgs", "II Kings", "Second Kings"]),
    ("1 Chronicles", ["1 Chron", "1 Chr", "I Chronicles"]),
    ("2 Chronicles", ["2 Chron", "2 Chr", "II Chronicles"]),
    ("Ezra", []),
    ("Nehemiah", ["Neh"]),
    ("Esther", ["Esth"]),
    ("Job", []),
    ("Psalms", ["Psalm", "Ps", "Pss"]),
    ("Proverbs", ["Prov", "Pr"]),
    ("Ecclesiastes", ["Eccl", "Ecc"]),
    ("Song of Solomon", ["Song of Songs", "Song"]),
    ("Isaiah", ["Isa"]),
    ("Jeremiah", ["Jer"]),
    ("Lamentations", ["Lam"]),
    ("Ezekiel", ["Ezek"]),
    ("Daniel", ["Dan"]),
    ("Hosea", ["Hos"]),
    ("Joel", []),
    ("Amos", []),
    ("Obadiah", ["Obad"]),
    ("Jonah", []),
    ("Micah", ["Mic"]),
    ("Nahum", ["Nah"]),
    ("Habakkuk", ["Hab"]),
    ("Zephaniah", ["Zeph"]),
    ("Haggai", ["Hag"]),
    ("Zechariah", ["Zech"]),
    ("Malachi", ["Mal"]),
    ("Matthew", ["Matt", "Mt"]),
    ("Mark", ["Mk"]),
    ("Luke", ["Lk"]),
    ("John", ["Jn"]),
    ("Acts", []),
    ("Romans", ["Rom"]),
    ("1 Corinthians", ["1 Cor", "I Corinthians", "First Corinthians"]),
    ("2 Corinthians", ["2 Cor", "II Corinthians", "Second Corinthians"]),
    ("Galatians", ["Gal"]),
    ("Ephesians", ["Eph"]),
    ("Philippians", ["Phil"]),
    ("Colossians", ["Col"]),
    ("1 Thessalonians", ["1 Thess", "1 Thes", "I Thessalonians"]),
    ("2 Thessalonians", ["2 Thess", "2 Thes", "II Thessalonians"]),
    ("1 Timothy", ["1 Tim", "I Timothy", "First Timothy"]),
    ("2 Timothy", ["2 Tim", "II Timothy", "Second Timothy"]),
    ("Titus", []),
    ("Philemon", ["Phlm", "Philem"]),
    ("Hebrews", ["Heb"]),
    ("James", ["Jas"]),
    ("1 Peter", ["1 Pet", "I Peter", "First Peter"]),
    ("2 Peter", ["2 Pet", "II Peter", "Second Peter"]),
    ("1 John", ["I John", "First John", "1 Jn"]),
    ("2 John", ["II John", "Second John", "2 Jn"]),
    ("3 John", ["III John", "Third John", "3 Jn"]),
    ("Jude", []),
    ("Revelation", ["Rev", "Revelations"]),
]

BOOK_ORDER: dict[str, int] = {name: i for i, (name, _) in enumerate(_BOOKS)}

# Chapters per book, canonical order. Speech-to-text often drops the colon
# ("Romans 828" for 8:28), so references are checked against these.
CHAPTER_COUNTS: dict[str, int] = dict(zip(BOOK_ORDER, map(int, "50 40 27 36 34 24 21 4 31 24 22 25 29 36 10 13 10 42 150 31 12 8 66 52 5 48 12 14 3 9 1 4 7 3 3 3 2 14 4 28 16 24 21 28 16 16 13 6 6 4 4 5 3 6 4 3 1 13 5 5 3 5 1 1 1 22".split())))

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _name, _aliases in _BOOKS:
    _ALIAS_TO_CANONICAL[_name.lower()] = _name
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias.lower()] = _name

# Longest-first so "1 John" wins over "John", "Song of Solomon" over "Song"
_ALL_NAMES = sorted(_ALIAS_TO_CANONICAL, key=len, reverse=True)
_REF_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _ALL_NAMES) + r")\.?\s+"
    r"(\d{1,3})"                      # chapter
    r"(?:(?::|\.(?=\d))(\d{1,3}(?:\s*[-–]\s*\d{1,3})?))?"  # optional :verse, :verse-verse, or ASR's .verse
    r"\b(?!\s*/\d)",                  # not a date ("Mark 12/3/2023")
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Reference:
    book: str
    chapter: int
    verses: str | None = None

    @property
    def display(self) -> str:
        return f"{self.book} {self.chapter}" + (f":{self.verses}" if self.verses else "")


def book_slug(book: str) -> str:
    return book.lower().replace(" ", "-")


def normalize_reference(book: str, chapter: str, verses: str | None) -> Reference | None:
    """Validate a parsed reference against the book's chapter count.

    - Single-chapter books take the number as a verse: "Jude 24" -> Jude 1:24.
    - A missing colon is repaired only when exactly one split is a real chapter:
      "Romans 828" -> Romans 8:28, but "Romans 124" (1:24 or 12:4) is dropped.
    - Anything else past the last chapter is dropped.
    """
    last = CHAPTER_COUNTS[book]
    number = int(chapter)
    if last == 1 and not verses:
        return Reference(book, 1, str(number)) if number > 1 else Reference(book, 1)
    if 1 <= number <= last:
        return Reference(book, number, verses)
    if verses or len(chapter) < 2:
        return None
    splits = [(int(chapter[:i]), chapter[i:]) for i in range(1, len(chapter))
              if not chapter[i:].startswith("0") and 1 <= int(chapter[:i]) <= last]
    if len(splits) != 1:
        return None
    return Reference(book, splits[0][0], splits[0][1])


@dataclass(frozen=True)
class ReferenceMatch:
    start: int  # span of the reference as written in the text
    end: int
    text: str  # "Rom. 8:1", "Romans 828"
    reference: Reference  # canonical and validated: Romans 8:1, Romans 8:28


def find_references(text: str) -> Iterator[ReferenceMatch]:
    """Every validated reference in text, in order, with where it was written.

    The one matcher behind `extract_references` and any renderer that marks
    references up in place. Matches that fail `normalize_reference` are skipped.
    """
    for match in _REF_RE.finditer(text):
        book = _ALIAS_TO_CANONICAL[match.group(1).lower()]
        verses = re.sub(r"\s*[-–]\s*", "-", match.group(3)) if match.group(3) else None
        ref = normalize_reference(book, match.group(2), verses)
        if ref is not None:
            yield ReferenceMatch(match.start(), match.end(), match.group(0), ref)


def extract_references(text: str) -> list[Reference]:
    """Return unique, validated references in order of first appearance."""
    return list(dict.fromkeys(m.reference for m in find_references(text)))


# Canonical names only: aliases like "Song", "Mark", or "Acts" are too common
# in series titles to trust without a chapter number.
_BOOK_NAME_RE = re.compile(
    r"(?<![\w])(" + "|".join(re.escape(name) for name, _ in sorted(_BOOKS, key=lambda b: -len(b[0]))) + r")(?![\w])"
)


def books_named(text: str) -> list[str]:
    """Canonical book names that appear verbatim in text, in canonical order."""
    found = {match.group(1) for match in _BOOK_NAME_RE.finditer(text)}
    return sorted(found, key=BOOK_ORDER.__getitem__)
