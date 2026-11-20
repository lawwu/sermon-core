import copy
import dataclasses
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from sermon_core import record as rec

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def berean():
    """A real content/recordings/<id>.yaml from lawwu/berean, as a v1 record."""
    raw = yaml.safe_load((FIXTURES / "berean-X9vaAsBiLVY.yaml").read_text())
    entry = load_json("berean-X9vaAsBiLVY.metadata.json")
    transcript = rec.Transcript(path="transcripts/X9vaAsBiLVY.txt", engine="parakeet_v3")
    return rec.from_berean_yaml(raw, entry, transcript=transcript)


@pytest.fixture
def beacon():
    """What Beacon has today: a bare yt-dlp entry, nothing curated."""
    entry = load_json("beacon-zcnLREVFdTQ.metadata.json")
    return rec.from_ytdlp(entry, church="beacon").to_dict()


def errors(data):
    """Validate with both this package and the reference jsonschema library.

    The two must agree on validity (passage checks are extra, so they run
    only on records the schema accepts).
    """
    ours = rec.validate(data)
    theirs = list(jsonschema.Draft202012Validator(rec.schema()).iter_errors(data))
    schema_ok = not theirs
    assert schema_ok or ours, f"jsonschema rejected what validate accepted: {theirs}"
    return ours


def test_schema_is_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(rec.schema())


def test_berean_record_passes(berean):
    assert errors(berean) == []
    record = rec.SermonRecord.from_dict(berean)
    assert record.source.upload_date == "2026-09-07"
    assert record.source.duration_s == 5443
    assert record.generated.series == "sunday-luke"
    assert record.passages == ["Luke 17:31-37"]
    assert record.generated.verses[1].ref == "Amos 5:18"
    assert record.visible


def test_berean_rename_is_mechanical(berean):
    """curated/generated carry over untouched; only title/date move under source."""
    raw = yaml.safe_load((FIXTURES / "berean-X9vaAsBiLVY.yaml").read_text())
    assert berean["curated"] == raw["curated"]
    assert berean["generated"] == raw["generated"]
    assert berean["source"]["title"] == raw["title"]
    assert berean["source"]["upload_date"] == raw["date"]


def test_beacon_record_passes(beacon):
    assert errors(beacon) == []
    record = rec.SermonRecord.from_dict(beacon)
    assert record.church == "beacon"
    assert record.platform == "youtube"
    assert record.source.upload_date == "2025-05-26"
    assert record.transcript is None
    assert record.curated == rec.Curated()
    assert record.title == "Beacon Sunday Service: May 25, 2025"


def test_round_trip(berean):
    record = rec.SermonRecord.from_dict(berean)
    assert rec.SermonRecord.from_dict(record.to_dict()) == record


def test_curated_overrides(beacon):
    beacon["curated"] = {"title": "Abide", "series": "john-2025", "passages": ["John 15:1-11"],
                         "published": False}
    assert errors(beacon) == []
    record = rec.SermonRecord.from_dict(beacon)
    assert (record.title, record.series, record.passages) == ("Abide", "john-2025", ["John 15:1-11"])
    assert not record.visible


def test_chapters():
    entry = load_json("beacon-zcnLREVFdTQ.metadata.json")
    entry["chapters"] = [{"start_time": 0, "end_time": 272.0, "title": "Worship"},
                         {"start_time": 272.0, "title": "Sermon", "end_time": 3131}]
    data = rec.from_ytdlp(entry, "beacon").to_dict()
    assert errors(data) == []
    assert data["source"]["chapters"][1] == {"start_s": 272.0, "title": "Sermon", "end_s": 3131}


@pytest.mark.parametrize("field", ["speakr", "passage", "hidden"])
def test_misspelled_curated_field_fails(berean, field):
    berean["curated"][field] = "x"
    problems = errors(berean)
    assert any(f"unknown field {field!r}" in p for p in problems), problems


@pytest.mark.parametrize("passage", [
    "Hezekiah 3:16",  # no such book
    "Luke 99:1",      # Luke has 24 chapters
    "Luke 17:31-37 and Acts 2",  # two references in one entry
    "see the title",
])
def test_bad_curated_passage_fails(berean, passage):
    berean["curated"]["passages"] = [passage]
    problems = errors(berean)
    assert any("curated.passages[0]" in p for p in problems), problems


def test_bad_generated_verse_fails(berean):
    berean["generated"]["verses"][0]["ref"] = "Obadiah 3:1"  # Obadiah has one chapter
    assert any("verses[0].ref" in p for p in errors(berean))


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r["source"].update(upload_date="20260907"), "upload_date"),
    (lambda r: r.update(platform="tiktok"), "platform"),
    (lambda r: r.update(church="Berean Church"), "church"),
    (lambda r: r["generated"].update(kind="sermon"), "kind"),
    (lambda r: r["transcript"].update(engine="whisper"), "engine"),
    (lambda r: r["curated"].update(published="no"), "published"),
    (lambda r: r["curated"].update(series="Sunday Luke"), "series"),
    (lambda r: r["curated"].update(duplicate_of=r["id"]), "duplicate itself"),
    (lambda r: r.pop("source"), "source"),
    (lambda r: r.update(extra=1), "unknown field 'extra'"),
])
def test_invalid_records_fail(berean, mutate, message):
    mutate(berean)
    problems = errors(berean)
    assert any(message in p for p in problems), problems


def test_newer_minor_is_refused_older_reader_must_upgrade(beacon):
    beacon["schema_version"] = f"1.{rec.SCHEMA_MINOR + 1}"
    assert "upgrade" in rec.validate(beacon)[0]
    beacon["schema_version"] = "2.0"
    assert "not v1" in rec.validate(beacon)[0]


def test_dataclasses_mirror_schema():
    """Every dataclass field is a schema property and vice versa."""
    props = rec.schema()["properties"]
    pairs = [
        (rec.SermonRecord, props),
        (rec.RecordSource, props["source"]["properties"]),
        (rec.Chapter, props["source"]["properties"]["chapters"]["items"]["properties"]),
        (rec.Transcript, props["transcript"]["properties"]),
        (rec.Curated, props["curated"]["properties"]),
        (rec.Generated, props["generated"]["properties"]),
        (rec.Verse, props["generated"]["properties"]["verses"]["items"]["properties"]),
    ]
    for cls, schema_props in pairs:
        assert {f.name for f in dataclasses.fields(cls)} == set(schema_props), cls.__name__


def test_cli(tmp_path, berean, beacon, capsys):
    good = tmp_path / "records.json"
    good.write_text(json.dumps([berean, beacon]))
    assert rec.main(["validate", str(good)]) == 0
    bad = copy.deepcopy(berean)
    bad["curated"]["speakr"] = "Peter Kim"
    bad_path = tmp_path / "bad.yaml"
    bad_path.write_text(yaml.safe_dump(bad))
    assert rec.main(["validate", str(good), str(bad_path)]) == 1
    assert "speakr" in capsys.readouterr().err
