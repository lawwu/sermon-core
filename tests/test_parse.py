from sermon_core.parse import parse_lines


def test_parses_timestamps_and_text():
    lines = [
        "[00:00:10.000 --> 00:00:15.500]   For God so loved the world,",
        "[00:00:15.500 --> 00:00:20.000]   that he gave his only Son.",
    ]
    segments = parse_lines(lines)
    assert len(segments) == 2
    assert segments[0].start == 10.0
    assert segments[0].end == 15.5
    assert segments[0].text == "For God so loved the world,"


def test_drops_annotation_only_segments():
    lines = [
        "[00:00:00.000 --> 00:00:10.000]   [MUSIC]",
        "[00:00:10.000 --> 00:00:12.000]   (applause)",
        "[00:00:12.000 --> 00:00:14.000]   ♪ amazing grace ♪",
        "[00:00:14.000 --> 00:00:18.000]   Please open your Bibles.",
    ]
    segments = parse_lines(lines)
    assert len(segments) == 1
    assert segments[0].text == "Please open your Bibles."


def test_strips_inline_annotations():
    lines = ["[00:00:00.000 --> 00:00:05.000]   Welcome [APPLAUSE] everyone."]
    segments = parse_lines(lines)
    assert segments[0].text == "Welcome everyone."


def test_collapses_whisper_repeat_loops():
    lines = [
        f"[00:00:{i:02d}.000 --> 00:00:{i + 1:02d}.000]   Amen." for i in range(10)
    ]
    segments = parse_lines(lines)
    assert len(segments) == 2  # first + one allowed repeat, rest collapsed
    assert segments[-1].end == 10.0


def test_hour_timestamps():
    lines = ["[01:02:03.250 --> 01:02:04.000]   text"]
    segments = parse_lines(lines)
    assert segments[0].start == 3723.25
