"""Shared sermon pipeline: ingest YouTube recordings, transcribe them, and load
them as Sermons with paragraphs, scripture references, and series.

The interface is what's exported here. Each site supplies its own output
(static HTML, a database export, ...) on top of `load`.
"""

from .corpus import Corpus, load
from .ingest import heal, ingest, ytdlp
from .model import Sermon
from .record import SermonRecord, validate as validate_record
from .paragraphs import Paragraph
from .scripture import (
    BOOK_ORDER,
    Reference,
    ReferenceMatch,
    book_slug,
    books_named,
    extract_references,
    find_references,
)
from .series import MessageSeries, group_series
from .source import Source

__all__ = [
    "BOOK_ORDER",
    "Corpus",
    "MessageSeries",
    "Paragraph",
    "Reference",
    "ReferenceMatch",
    "Sermon",
    "SermonRecord",
    "Source",
    "book_slug",
    "books_named",
    "extract_references",
    "find_references",
    "group_series",
    "heal",
    "ingest",
    "load",
    "validate_record",
    "ytdlp",
]
