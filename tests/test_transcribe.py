from sermon_core.transcribe import hms, yield_ok


def test_hms_formats_whisper_style():
    assert hms(0) == "00:00:00.000"
    assert hms(71.25) == "00:01:11.250"
    assert hms(3723.5) == "01:02:03.500"


def test_hms_rounds_milliseconds():
    assert hms(1.0004) == "00:00:01.000"
    assert hms(1.9996) == "00:00:02.000"


def test_yield_ok_accepts_healthy_density():
    # ~15 bytes/sec is a normal sermon
    assert yield_ok("word " * 900, 300)


def test_yield_ok_rejects_hallucination_loop_density():
    # the "Thank you." failure produced ~1.5 bytes/sec
    assert not yield_ok("Thank you. " * 40, 300)


def test_yield_ok_zero_duration_requires_text():
    assert yield_ok("something", 0)
    assert not yield_ok("   ", 0)


# --- MLX cache handling: tests run without mlx or parakeet-mlx installed ---

import sys
import types
from pathlib import Path

import pytest

from sermon_core import transcribe as t


def _fake_mlx(monkeypatch, top_level=True):
    """Install a stand-in mlx.core that records memory calls."""
    calls = []
    record = lambda name: lambda *args: calls.append((name, *args))  # noqa: E731
    core = types.ModuleType("mlx.core")
    core.metal = types.SimpleNamespace(
        clear_cache=record("metal.clear_cache"),
        set_cache_limit=record("metal.set_cache_limit"),
    )
    if top_level:
        core.clear_cache = record("clear_cache")
        core.set_cache_limit = record("set_cache_limit")
    pkg = types.ModuleType("mlx")
    pkg.core = core
    monkeypatch.setitem(sys.modules, "mlx", pkg)
    monkeypatch.setitem(sys.modules, "mlx.core", core)
    return calls


class _FakeModel:
    def __init__(self, fail=False):
        self.fail = fail

    def transcribe(self, path, chunk_duration, overlap_duration):
        if self.fail:
            raise RuntimeError("decode failed")
        sentence = types.SimpleNamespace(start=0.0, end=2.5, text=" In the beginning ")
        return types.SimpleNamespace(sentences=[sentence])


def test_cache_is_emptied_after_every_file(monkeypatch):
    calls = _fake_mlx(monkeypatch)
    monkeypatch.setattr(t, "_MODEL", _FakeModel())
    text = t.transcribe_parakeet(Path("a.wav"))
    t.transcribe_parakeet(Path("b.wav"))
    assert text == "[00:00:00.000 --> 00:00:02.500]   In the beginning\n"
    assert calls == [("clear_cache",), ("clear_cache",)]


def test_cache_is_emptied_when_transcription_fails(monkeypatch):
    calls = _fake_mlx(monkeypatch)
    monkeypatch.setattr(t, "_MODEL", _FakeModel(fail=True))
    with pytest.raises(RuntimeError):
        t.transcribe_parakeet(Path("a.wav"))
    assert calls == [("clear_cache",)]


def test_model_load_caps_the_cache_once(monkeypatch):
    calls = _fake_mlx(monkeypatch)
    loads = []
    parakeet = types.ModuleType("parakeet_mlx")
    parakeet.from_pretrained = lambda name: loads.append(name) or _FakeModel()
    monkeypatch.setitem(sys.modules, "parakeet_mlx", parakeet)
    monkeypatch.setattr(t, "_MODEL", None)
    t._parakeet()
    t._parakeet()
    assert loads == ["mlx-community/parakeet-tdt-0.6b-v3"]
    assert calls == [("set_cache_limit", t.MLX_CACHE_LIMIT_BYTES)]


def test_older_mlx_uses_the_metal_namespace(monkeypatch):
    calls = _fake_mlx(monkeypatch, top_level=False)
    monkeypatch.setattr(t, "_MODEL", _FakeModel())
    t.transcribe_parakeet(Path("a.wav"))
    assert calls == [("metal.clear_cache",)]
