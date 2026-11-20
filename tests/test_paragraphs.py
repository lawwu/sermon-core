from sermon_core.paragraphs import group_paragraphs
from sermon_core.parse import Segment


def seg(start, end, text):
    return Segment(start=start, end=end, text=text)


def test_long_gap_starts_new_paragraph():
    segments = [
        seg(0, 5, "First thought."),
        seg(10, 15, "After a long silence."),
    ]
    paragraphs = group_paragraphs(segments)
    assert len(paragraphs) == 2
    assert paragraphs[0].text == "First thought."
    assert paragraphs[1].start == 10


def test_short_gap_keeps_paragraph_together():
    segments = [
        seg(0, 5, "One sentence"),
        seg(5.5, 10, "continues here."),
    ]
    paragraphs = group_paragraphs(segments)
    assert len(paragraphs) == 1
    assert paragraphs[0].text == "One sentence continues here."


def test_breaks_at_sentence_after_target_length():
    # 20 segments x 6s = 120s of continuous speech ending in sentences
    segments = [
        seg(i * 6, i * 6 + 6, f"Sentence number {i}.") for i in range(20)
    ]
    paragraphs = group_paragraphs(segments)
    assert len(paragraphs) > 1
    # every paragraph carries the timestamp of its first segment
    assert paragraphs[0].start == 0
    assert all(p.text for p in paragraphs)


def test_hard_break_without_sentence_boundaries():
    # run-on speech with no punctuation must still break eventually
    segments = [seg(i * 6, i * 6 + 6, "and then and then") for i in range(60)]
    paragraphs = group_paragraphs(segments)
    assert len(paragraphs) > 1
