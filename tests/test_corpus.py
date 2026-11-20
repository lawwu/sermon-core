import json
from dataclasses import dataclass
from pathlib import Path

from sermon_core import load


@dataclass
class FakeSource:
    metadata_path: Path
    transcripts_dir: Path
    name: str = "Test Church"
    youtube_channel: str = ""
    whisper_bin: Path | None = None
    whisper_model: Path | None = None


def write_source(tmp_path, metadata, transcripts):
    (tmp_path / "t").mkdir()
    for video_id, text in transcripts.items():
        (tmp_path / "t" / f"{video_id}.txt").write_text(text, encoding="utf-8")
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    return FakeSource(meta, tmp_path / "t")


LINE = "[00:00:01.000 --> 00:00:05.000]   Turn with me to John 3:16. God so loved the world.\n"


def test_load_keeps_usable_recordings_oldest_first_and_says_why_others_are_skipped(tmp_path):
    source = write_source(
        tmp_path,
        {
            "new": {"title": "Love (John 3:16)", "upload_date": "20260202", "duration": 1800},
            "old": {"title": "Grace", "upload_date": "20250101",
                    "webpage_url": "https://vimeo.com/1"},
            "nodate": {"title": "Undated"},
            "missing": {"title": "No transcript", "upload_date": "20260101"},
            "empty": {"title": "Silent", "upload_date": "20260101"},
        },
        {"new": LINE, "old": LINE, "nodate": LINE, "empty": ""},
    )
    corpus = load(source)
    assert [s.id for s in corpus.sermons] == ["old", "new"]
    new = corpus.sermons[1]
    assert new.url == "https://www.youtube.com/watch?v=new"
    assert [r.display for r in new.references] == ["John 3:16"]
    assert new.paragraphs[0].text.startswith("Turn with me")
    assert corpus.sermons[0].platform == "vimeo"
    assert sorted(corpus.skipped) == ["empty: empty transcript", "missing: no transcript",
                                      "nodate: no upload date"]


def test_load_limit(tmp_path):
    source = write_source(
        tmp_path,
        {"a": {"title": "A", "upload_date": "20260101"}, "b": {"title": "B", "upload_date": "20260102"}},
        {"a": LINE, "b": LINE},
    )
    assert len(load(source, limit=1).sermons) == 1
