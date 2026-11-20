"""Sermon record v1: one versioned record per recording, shared by every site.

The contract is `schema/sermon-record.v1.json`. This module mirrors it as
dataclasses, validates records against it, and builds records from what
sites already have on disk (a yt-dlp metadata entry, a Berean
`content/recordings/<id>.yaml`).

A record has four layers with different owners:

- `source`: copied from yt-dlp. Tools refresh it; people never edit it.
- `transcript`: the transcript file and how it was made.
- `curated`: edited by people. Tools never overwrite it.
- `generated`: derived by tools and rewritten on every run.

`validate` reads the JSON Schema itself (no dependency) and then checks what
JSON Schema can't: that passages name a real book and chapter, and that the
record's schema version is one this code knows.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal

from .scripture import find_references

SCHEMA_MAJOR = 1
SCHEMA_MINOR = 0
SCHEMA_VERSION = f"{SCHEMA_MAJOR}.{SCHEMA_MINOR}"

Platform = Literal["youtube", "vimeo"]
Engine = Literal["parakeet_v3", "wcpp_mc0", "low_yield", "failed"]
Kind = Literal["sunday", "bible_study", "event", "other"]


@dataclass
class Chapter:
    start_s: float
    title: str
    end_s: float | None = None


@dataclass
class RecordSource:
    """From yt-dlp, never hand-edited."""

    title: str
    upload_date: str  # ISO date, YYYY-MM-DD
    duration_s: int | None = None
    thumbnail: str | None = None
    chapters: list[Chapter] = field(default_factory=list)


@dataclass
class Transcript:
    path: str  # relative to the church's data directory
    format: Literal["whisper"] = "whisper"
    engine: Engine | None = None
    transcribed_at: str | None = None  # ISO date-time


@dataclass
class Curated:
    """Edited by people; tools never overwrite it. None means not curated."""

    title: str | None = None
    speaker: str | None = None
    series: str | None = None
    passages: list[str] = field(default_factory=list)
    summary: str | None = None
    published: bool = True
    duplicate_of: str | None = None


@dataclass
class Verse:
    ref: str
    t: float
    source: Literal["transcript"]
    mentions: int


@dataclass
class Generated:
    """Derived by tools and rewritten on every run."""

    kind: Kind | None = None
    series: str | None = None
    passages: list[str] = field(default_factory=list)
    verses: list[Verse] = field(default_factory=list)


@dataclass
class SermonRecord:
    id: str
    church: str
    platform: Platform
    url: str
    source: RecordSource
    transcript: Transcript | None = None
    curated: Curated = field(default_factory=Curated)
    generated: Generated = field(default_factory=Generated)
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: dict) -> "SermonRecord":
        """Build from a dict, raising RecordError if it is not a valid record."""
        errors = validate(data)
        if errors:
            raise RecordError(errors)
        src = data["source"]
        transcript = data.get("transcript")
        generated = data.get("generated") or {}
        return cls(
            schema_version=data["schema_version"],
            id=data["id"],
            church=data["church"],
            platform=data["platform"],
            url=data["url"],
            source=RecordSource(
                title=src["title"],
                upload_date=src["upload_date"],
                duration_s=src.get("duration_s"),
                thumbnail=src.get("thumbnail"),
                chapters=[Chapter(**c) for c in src.get("chapters", [])],
            ),
            transcript=Transcript(**transcript) if transcript else None,
            curated=Curated(**(data.get("curated") or {})),
            generated=Generated(
                kind=generated.get("kind"),
                series=generated.get("series"),
                passages=list(generated.get("passages", [])),
                verses=[Verse(**v) for v in generated.get("verses", [])],
            ),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        # schema_version first, so a file says what it is on its first line.
        return {"schema_version": data.pop("schema_version"), **data}

    @property
    def title(self) -> str:
        """What a site shows: the curated title, else the source title."""
        return self.curated.title or self.source.title

    @property
    def series(self) -> str | None:
        return self.curated.series or self.generated.series

    @property
    def passages(self) -> list[str]:
        return self.curated.passages or self.generated.passages

    @property
    def visible(self) -> bool:
        return self.curated.published and not self.curated.duplicate_of


class RecordError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


# --- Building records from what sites have today ---------------------------


def iso_date(upload_date: str) -> str:
    """yt-dlp's YYYYMMDD -> YYYY-MM-DD; ISO dates pass through."""
    d = str(upload_date)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d) else d


def platform_of(url: str) -> Platform:
    return "vimeo" if "vimeo.com" in url else "youtube"


def source_from_ytdlp(entry: dict) -> RecordSource:
    """The `source` layer from one yt-dlp metadata.json entry."""
    return RecordSource(
        title=entry["title"],
        upload_date=iso_date(entry["upload_date"]),
        duration_s=int(entry["duration"]) if entry.get("duration") is not None else None,
        thumbnail=entry.get("thumbnail"),
        chapters=[
            Chapter(start_s=c["start_time"], title=c.get("title", ""), end_s=c.get("end_time"))
            for c in entry.get("chapters") or []
        ],
    )


def from_ytdlp(entry: dict, church: str, transcript: Transcript | None = None) -> SermonRecord:
    """A record with only source facts: what a church without curation has."""
    url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"
    return SermonRecord(
        id=entry["id"],
        church=church,
        platform=platform_of(url),
        url=url,
        source=source_from_ytdlp(entry),
        transcript=transcript,
    )


def from_berean_yaml(raw: dict, entry: dict | None = None, church: str = "berean",
                     transcript: Transcript | None = None) -> dict:
    """A Berean `content/recordings/<id>.yaml` (already parsed) as a v1 record dict.

    The renames are mechanical: top-level `title`/`date` become
    `source.title`/`source.upload_date`; `curated` and `generated` carry over
    as they are. Pass the recording's yt-dlp `entry` to fill in duration,
    thumbnail, chapters, and URL. Returns a dict so it can be validated as is.
    """
    source = asdict(source_from_ytdlp(entry)) if entry else {}
    source.update(title=raw["title"], upload_date=iso_date(raw["date"]))
    url = (entry or {}).get("webpage_url") or f"https://www.youtube.com/watch?v={raw['id']}"
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": raw["id"],
        "church": church,
        "platform": platform_of(url),
        "url": url,
        "source": source,
        "transcript": asdict(transcript) if transcript else None,
        "curated": dict(raw.get("curated") or {}),
        "generated": dict(raw.get("generated") or {}),
    }
    return record


# --- Validation ------------------------------------------------------------


def schema_path() -> Path:
    """The bundled JSON Schema (in the wheel) or the repo's copy (in a checkout)."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "schema", here.parents[1] / "schema"):
        path = candidate / f"sermon-record.v{SCHEMA_MAJOR}.json"
        if path.exists():
            return path
    raise FileNotFoundError(f"sermon-record.v{SCHEMA_MAJOR}.json not found next to {here}")


@cache
def schema() -> dict:
    return json.loads(schema_path().read_text(encoding="utf-8"))


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _check(value: Any, rule: dict, path: str, root: dict, errors: list[str]) -> None:
    """The subset of JSON Schema the record schema uses. Appends to errors."""
    if "$ref" in rule:
        target = root
        for part in rule["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        _check(value, target, path, root, errors)
    if "oneOf" in rule:
        matches = 0
        for option in rule["oneOf"]:
            sub: list[str] = []
            _check(value, option, path, root, sub)
            matches += not sub
        if matches != 1:
            errors.append(f"{path}: {value!r} is not a valid value")
            return
    if "type" in rule:
        types = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
        if not any(_TYPES[t](value) for t in types):
            errors.append(f"{path}: expected {' or '.join(types)}, got {value!r}")
            return
    if "const" in rule and value != rule["const"]:
        errors.append(f"{path}: must be {rule['const']!r}, got {value!r}")
    if "enum" in rule and value not in rule["enum"]:
        allowed = ", ".join("null" if e is None else e for e in rule["enum"])
        errors.append(f"{path}: {value!r} is not one of {allowed}")
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0):
            errors.append(f"{path}: must not be empty")
        if "pattern" in rule and not re.search(rule["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {rule['pattern']}")
    if _TYPES["number"](value) and "minimum" in rule and value < rule["minimum"]:
        errors.append(f"{path}: {value!r} is below {rule['minimum']}")
    if isinstance(value, dict):
        props = rule.get("properties", {})
        for key in rule.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field {key!r}")
        for key, item in value.items():
            if key in props:
                _check(item, props[key], f"{path}.{key}", root, errors)
            elif rule.get("additionalProperties") is False:
                errors.append(f"{path}: unknown field {key!r}; allowed: {', '.join(props)}")
    if isinstance(value, list) and "items" in rule:
        for i, item in enumerate(value):
            _check(item, rule["items"], f"{path}[{i}]", root, errors)


def passage_problem(passage: str) -> str | None:
    """Why a passage isn't one valid Bible reference, or None if it is."""
    text = passage.strip()
    matches = list(find_references(text))
    if not matches:
        return "is not a Bible reference like 'Luke 17:31-37' (unknown book, or chapter out of range)"
    if len(matches) > 1 or matches[0].start != 0 or matches[0].end != len(text):
        return "must be exactly one Bible reference"
    return None


def validate(data: Any) -> list[str]:
    """Every problem with a record, as readable messages. Empty means valid."""
    root = schema()
    errors: list[str] = []
    version = data.get("schema_version") if isinstance(data, dict) else None
    if isinstance(version, str) and (m := re.fullmatch(r"(\d+)\.(\d+)", version)):
        major, minor = int(m[1]), int(m[2])
        if major != SCHEMA_MAJOR:
            return [f"record: schema_version {version} is not v{SCHEMA_MAJOR}; use a sermon-core that reads v{major}"]
        if minor > SCHEMA_MINOR:
            return [f"record: schema_version {version} is newer than this sermon-core ({SCHEMA_VERSION}); upgrade it"]
    _check(data, root, "record", root, errors)
    if errors:
        return errors
    for layer in ("curated", "generated"):
        for i, passage in enumerate((data.get(layer) or {}).get("passages") or []):
            if problem := passage_problem(passage):
                errors.append(f"record.{layer}.passages[{i}]: {passage!r} {problem}")
    for i, verse in enumerate((data.get("generated") or {}).get("verses") or []):
        if problem := passage_problem(verse["ref"]):
            errors.append(f"record.generated.verses[{i}].ref: {verse['ref']!r} {problem}")
    if (data.get("curated") or {}).get("duplicate_of") == data["id"]:
        errors.append("record.curated.duplicate_of: a recording cannot duplicate itself")
    return errors


def _load_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError:
            raise SystemExit(f"{path}: reading YAML needs PyYAML (pip install pyyaml)") from None
        return yaml.safe_load(text)
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    """`sermon-record validate FILE...`: exit 1 if any record is invalid."""
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] != "validate" or len(args) < 2:
        print("usage: sermon-record validate FILE.json|FILE.yaml ...", file=sys.stderr)
        return 2
    total = bad = 0
    for name in args[1:]:
        path = Path(name)
        data = _load_file(path)
        for record in data if isinstance(data, list) else [data]:
            total += 1
            errors = validate(record)
            bad += bool(errors)
            for error in errors:
                print(f"{path}: {error}", file=sys.stderr)
    print(f"{total - bad}/{total} valid", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
