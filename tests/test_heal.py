from pathlib import Path

from sermon_core.ingest import is_broken


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_missing_transcript_is_broken(tmp_path):
    assert is_broken(tmp_path / "nope.txt", 3600)


def test_healthy_transcript_passes(tmp_path):
    # ~18 bytes/sec for a one-hour sermon
    p = write(tmp_path, "ok.txt", "word " * 13000)
    assert not is_broken(p, 3600)


def test_sparse_transcript_is_broken(tmp_path):
    # the zero-byte / silent-failure mode (~1.5 bytes/sec and below)
    p = write(tmp_path, "sparse.txt", "a few words\n")
    assert is_broken(p, 3600)


def test_thank_you_loop_is_broken(tmp_path):
    # dense enough to pass the bytes/sec check, but nearly all hallucination.
    # (real loops are sparse AND repetitive; this isolates the repetition rule)
    line = "[00:00:00.000 --> 00:00:29.980]   Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you.\n"
    p = write(tmp_path, "loop.txt", line * 100)
    assert is_broken(p, 3600)


def test_unknown_duration_trusts_existing_file(tmp_path):
    p = write(tmp_path, "short.txt", "brief but real content")
    assert not is_broken(p, 0)
