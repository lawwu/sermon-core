"""ASR engine: Parakeet TDT 0.6B v3 (MLX), whisper.cpp fallback.

Chosen from a head-to-head benchmark on sermon audio:
Parakeet was the fastest engine tested (~48x real-time including model load)
and the only one that produced zero hallucinations on silent/quiet audio —
the failure mode that silently destroyed 64 archive transcripts when
whisper's decoder locked onto a "Thank you." loop during pre-service
silence. whisper.cpp with `--max-context 0` is the configured fallback for
audio Parakeet yields too little text on.

Output is whisper-format `[HH:MM:SS.mmm --> HH:MM:SS.mmm]  text` lines so
every downstream consumer (parse.py, and older whisper-based archives)
keeps working unchanged.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .source import Source

CHUNK_SECONDS = 300.0   # long chunks: fewer seams, fewer dropped repeats
OVERLAP_SECONDS = 30.0
MIN_BYTES_PER_SEC = 5.0  # healthy sermons yield ~15-35 bytes/sec of audio

_MODEL = None


def hms(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def yield_ok(text: str, duration_seconds: float) -> bool:
    """Reject suspiciously sparse output (silent-failure guard)."""
    if duration_seconds <= 0:
        return bool(text.strip())
    return len(text.encode()) / duration_seconds >= MIN_BYTES_PER_SEC


def _parakeet():
    global _MODEL
    if _MODEL is None:
        from parakeet_mlx import from_pretrained

        _MODEL = from_pretrained("mlx-community/parakeet-tdt-0.6b-v3")
    return _MODEL


def transcribe_parakeet(wav: Path) -> str:
    result = _parakeet().transcribe(
        str(wav), chunk_duration=CHUNK_SECONDS, overlap_duration=OVERLAP_SECONDS
    )
    lines = [
        f"[{hms(s.start)} --> {hms(s.end)}]   {s.text.strip()}"
        for s in result.sentences
        if s.text.strip()
    ]
    return "\n".join(lines) + "\n" if lines else ""


def transcribe_whisper_cpp(wav: Path, config: Source) -> str:
    """Fallback engine; requires whisper_bin/whisper_model in the church config."""
    if not (config.whisper_bin and config.whisper_model):
        return ""
    # Machine-local and optional: a checkout without it falls back to low_yield, not a crash.
    if not (Path(config.whisper_bin).exists() and Path(config.whisper_model).exists()):
        return ""
    proc = subprocess.run(
        [str(config.whisper_bin), "-m", str(config.whisper_model),
         "-t", "7", "-mc", "0", "-f", str(wav)],
        capture_output=True, text=True, timeout=3600,
    )
    return proc.stdout if proc.returncode == 0 else ""


def transcribe(wav: Path, duration_seconds: float, config: Source) -> tuple[str, str]:
    """Transcribe with validation; returns (text, engine_used). Empty text = failure."""
    text = transcribe_parakeet(wav)
    if yield_ok(text, duration_seconds):
        return text, "parakeet_v3"
    fallback = transcribe_whisper_cpp(wav, config)
    if yield_ok(fallback, duration_seconds):
        return fallback, "wcpp_mc0"
    # Neither passed: keep the longer output but flag it as low yield
    best = text if len(text) >= len(fallback) else fallback
    return (best, "low_yield") if best.strip() else ("", "failed")
