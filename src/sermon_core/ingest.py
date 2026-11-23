"""Onboard/refresh a church: discover channel videos, transcribe new ones.

State lives in the filesystem: a video is done when its transcript file
exists and it appears in the metadata cache. No queue files. Safe to re-run
anytime; it only processes what's missing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .source import Source
from .transcribe import transcribe

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
CACHE_FIELDS = ("id", "title", "upload_date", "duration", "thumbnail", "webpage_url")

# yt-dlp live_status values for a stream YouTube is not done with. A
# `post_live` stream (ended, still processing) serves its audio only as
# thousands of small DASH fragments: a 71-minute sermon came down at ~14 KB/s
# and hit the 30-minute download timeout, while a processed (`was_live`)
# stream of the same length downloads in seconds. Skip these; the next run
# gets them.
NOT_READY = frozenset({"is_upcoming", "is_live", "post_live"})


def ytdlp(*args: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    """Run yt-dlp. A timeout comes back as a failed run, not an exception,
    so one slow video can't abort a whole ingest."""
    cmd = [sys.executable, "-m", "yt_dlp", *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"yt-dlp timed out after {timeout}s")


def discover(channel_url: str) -> list[dict]:
    """Flat-list the channel's videos and streams tabs, newest first."""
    entries: dict[str, dict] = {}
    errors: list[str] = []
    base = channel_url.rstrip("/")
    for tab in ("videos", "streams"):
        proc = ytdlp("--flat-playlist", "-J", f"{base}/{tab}")
        if proc.returncode != 0:
            errors.append(f"{tab}: {proc.stderr.strip().splitlines()[-1:] or ['?']}")
            continue
        data = json.loads(proc.stdout)
        for entry in data.get("entries") or []:
            if entry.get("id"):
                entries.setdefault(entry["id"], entry)
    # A channel with no reachable tabs means yt-dlp is broken or blocked, not
    # that the church stopped preaching. Failing loudly beats a silent
    # "0 videos on channel" that reads as a successful no-op weekly run.
    if not entries and errors:
        raise RuntimeError(f"channel discovery failed for {channel_url}: {'; '.join(errors)}")
    return list(entries.values())


def fetch_metadata(video_url: str) -> dict | None:
    """The cached fields, plus `live_status` (not cached; ingest pops it)."""
    proc = ytdlp("--no-download", "-J", video_url, timeout=120)
    if proc.returncode != 0:
        return None
    info = json.loads(proc.stdout)
    return {**{k: info.get(k) for k in CACHE_FIELDS}, "live_status": info.get("live_status")}


def download_wav16k(video_url: str, work_dir: Path) -> Path | None:
    out = work_dir / "audio"
    proc = ytdlp("-f", "bestaudio/best", "--no-playlist", "-q", "--no-warnings",
                  "-o", f"{out}.%(ext)s", video_url)
    if proc.returncode != 0:
        return None
    files = list(work_dir.glob("audio.*"))
    if not files:
        return None
    wav = work_dir / "audio16k.wav"
    try:
        conv = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(files[0]),
             "-ar", "16000", "-ac", "1", str(wav)],
            capture_output=True, text=True, timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return None
    return wav if conv.returncode == 0 and wav.exists() else None


def load_cache(config: Source) -> dict:
    if config.metadata_path.exists():
        return json.loads(config.metadata_path.read_text(encoding="utf-8"))
    return {}


def save_cache(config: Source, cache: dict) -> None:
    config.metadata_path.parent.mkdir(parents=True, exist_ok=True)
    config.metadata_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def is_broken(path: Path, duration_seconds: float) -> bool:
    """Detect the two archive failure modes: sparse/empty output (silent
    failures) and whisper's "Thank you." hallucination loop."""
    if not path.exists():
        return True
    if duration_seconds <= 0:
        return False
    if path.stat().st_size / duration_seconds < 5.0:
        return True
    text = path.read_text(errors="ignore")
    lines = text.count("\n") or 1
    return 100 * text.count("Thank you") / lines >= 25


def heal(config: Source, limit: int | None = None, dry_run: bool = False) -> dict:
    """Re-transcribe broken transcripts in place. The original is kept as
    <id>.txt.orig; a video with an .orig is never healed twice (genuinely
    sparse audio would otherwise re-trigger the heuristic forever)."""
    cache = load_cache(config)
    suspects = []
    for vid, info in cache.items():
        duration = info.get("duration") or 0
        if duration < 600:
            continue
        path = config.transcripts_dir / f"{vid}.txt"
        backup = path.parent / f"{path.name}.orig"
        if backup.exists() or not is_broken(path, duration):
            continue
        suspects.append((str(info.get("upload_date") or ""), vid, duration,
                         info.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"))
    suspects.sort(reverse=True)  # newest first
    print(f"{config.name}: {len(suspects)} broken transcripts to heal", flush=True)
    if dry_run:
        for upload_date, vid, duration, _ in suspects:
            print(f"  {upload_date} {vid} ({round(duration / 60)}min)", flush=True)
        return {"suspects": len(suspects), "healed": 0, "failed": 0}

    healed = failed = 0
    for upload_date, vid, duration, url in suspects:
        if limit and healed >= limit:
            break
        t0 = time.monotonic()
        path = config.transcripts_dir / f"{vid}.txt"
        with tempfile.TemporaryDirectory(prefix=f"heal_{vid}_") as tmp:
            wav = download_wav16k(url, Path(tmp))
            if not wav:
                failed += 1
                print(f"  {upload_date} {vid}: download failed", flush=True)
                continue
            text, engine = transcribe(wav, duration, config)
        if not text:
            failed += 1
            print(f"  {upload_date} {vid}: transcription failed", flush=True)
            continue
        old_bytes = path.stat().st_size if path.exists() else 0
        if path.exists():
            path.rename(path.parent / f"{path.name}.orig")
        path.write_text(text, encoding="utf-8")
        healed += 1
        print(f"  {upload_date} {vid}: {old_bytes} -> {len(text.encode())} bytes "
              f"via {engine} in {time.monotonic() - t0:.0f}s", flush=True)

    summary = {"suspects": len(suspects), "healed": healed, "failed": failed}
    print(f"heal complete: {summary}", flush=True)
    return summary


def ingest(config: Source, limit: int | None = None, min_minutes: float = 15.0) -> dict:
    """Returns summary counts. Processes newest-first up to `limit` new videos."""
    config.transcripts_dir.mkdir(parents=True, exist_ok=True)
    cache = load_cache(config)
    entries = discover(config.youtube_channel)
    print(f"{config.name}: {len(entries)} videos on channel", flush=True)

    done = skipped_short = failed = not_ready = 0
    for entry in entries:
        if limit and done >= limit:
            break
        vid = entry["id"]
        transcript_path = config.transcripts_dir / f"{vid}.txt"
        if transcript_path.exists() and vid in cache:
            continue
        flat_duration = entry.get("duration")
        if flat_duration and flat_duration < min_minutes * 60:
            skipped_short += 1
            continue

        t0 = time.monotonic()
        url = entry.get("url") or f"https://www.youtube.com/watch?v={vid}"
        # A stream cached while live has no duration yet; refetch once it has ended.
        cached = cache.get(vid)
        meta = cached if cached and cached.get("duration") else fetch_metadata(url)
        if not meta or not meta.get("upload_date"):
            failed += 1
            print(f"  {vid}: metadata failed", flush=True)
            continue
        meta = dict(meta)
        live_status = meta.pop("live_status", None)
        if live_status in NOT_READY:
            not_ready += 1
            print(f"  {vid}: {live_status} on YouTube, not ready yet; next run will retry", flush=True)
            continue
        duration = meta.get("duration") or flat_duration or 0
        if duration < min_minutes * 60:
            skipped_short += 1
            continue

        with tempfile.TemporaryDirectory(prefix=f"ingest_{vid}_") as tmp:
            wav = download_wav16k(url, Path(tmp))
            if not wav:
                failed += 1
                print(f"  {vid}: download failed", flush=True)
                continue
            text, engine = transcribe(wav, duration, config)

        if not text:
            failed += 1
            print(f"  {vid}: transcription failed", flush=True)
            continue
        transcript_path.write_text(text, encoding="utf-8")
        cache[vid] = meta
        save_cache(config, cache)  # checkpoint after every video
        done += 1
        secs = time.monotonic() - t0
        print(f"  {vid}: {meta['title'][:60]!r} {round(duration/60)}min -> "
              f"{len(text.encode())//1000}KB via {engine} in {secs:.0f}s", flush=True)

    summary = {"transcribed": done, "skipped_short": skipped_short, "failed": failed,
               "not_ready": not_ready, "total_in_cache": len(cache)}
    print(f"ingest complete: {summary}", flush=True)
    return summary
