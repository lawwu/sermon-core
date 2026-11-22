import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

# The package re-exports the ingest() function under the module's own name.
ing = importlib.import_module("sermon_core.ingest")


def test_ytdlp_timeout_is_a_failed_run_not_an_exception(monkeypatch):
    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(ing.subprocess, "run", slow)
    proc = ing.ytdlp("-f", "bestaudio", "https://example.com/v", timeout=5)
    assert proc.returncode == 124
    assert "timed out after 5s" in proc.stderr


def _source(tmp_path: Path):
    return SimpleNamespace(
        name="Test Church",
        youtube_channel="https://www.youtube.com/@test",
        metadata_path=tmp_path / "metadata.json",
        transcripts_dir=tmp_path / "transcripts",
        whisper_bin=None,
        whisper_model=None,
    )


def _meta(vid: str, live_status: str) -> dict:
    return {"id": vid, "title": f"Sermon {vid}", "upload_date": "20261122",
            "duration": 3600, "thumbnail": None, "webpage_url": None,
            "live_status": live_status}


def test_ingest_skips_processing_streams_and_survives_a_failed_download(monkeypatch, tmp_path):
    statuses = {"today": "post_live", "slow": "was_live", "ready": "was_live"}
    monkeypatch.setattr(ing, "discover", lambda url: [{"id": v} for v in statuses])
    monkeypatch.setattr(ing, "fetch_metadata", lambda url: _meta(url.rsplit("=", 1)[1], statuses[url.rsplit("=", 1)[1]]))
    downloads = []

    def download(url, work_dir):
        downloads.append(url.rsplit("=", 1)[1])
        if url.endswith("slow"):
            return None  # what a yt-dlp timeout now looks like
        wav = work_dir / "audio16k.wav"
        wav.write_bytes(b"")
        return wav

    monkeypatch.setattr(ing, "download_wav16k", download)
    monkeypatch.setattr(ing, "transcribe", lambda wav, duration, config: ("[00:00:00.000 --> 00:00:01.000]   Amen\n", "parakeet_v3"))

    summary = ing.ingest(_source(tmp_path))

    assert summary["transcribed"] == 1
    assert summary["failed"] == 1
    assert summary["not_ready"] == 1
    assert downloads == ["slow", "ready"]  # the post_live stream is never downloaded
    cache = json.loads((tmp_path / "metadata.json").read_text())
    assert list(cache) == ["ready"]
    assert "live_status" not in cache["ready"]  # cache keeps CACHE_FIELDS only
    assert (tmp_path / "transcripts" / "ready.txt").exists()
