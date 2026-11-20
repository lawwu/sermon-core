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
