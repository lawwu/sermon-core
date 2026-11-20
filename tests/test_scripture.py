from sermon_core.scripture import (
    find_references,
    books_named,
    book_slug,
    extract_references,
)


def test_extracts_book_chapter_verse_range():
    refs = extract_references(
        "Community Church Bible Study 11/15/2023 Galatians 3:10-14"
    )
    assert len(refs) == 1
    assert refs[0].book == "Galatians"
    assert refs[0].chapter == 3
    assert refs[0].verses == "10-14"
    assert refs[0].display == "Galatians 3:10-14"


def test_numbered_books_win_over_bare_names():
    refs = extract_references("A study in 1 John 4:7")
    assert refs[0].book == "1 John"


def test_abbreviations_normalize():
    refs = extract_references("Sunday Service Rom. 8:1 and Ps 23")
    books = [r.book for r in refs]
    assert books == ["Romans", "Psalms"]


def test_chapter_only():
    refs = extract_references("Sermon on John 3")
    assert refs[0].display == "John 3"
    assert refs[0].verses is None


def test_no_false_positive_without_number():
    assert extract_references("A sermon about job hunting and acts of kindness") == []


def test_dedupes_repeats():
    refs = extract_references("Romans 8 ... Romans 8 again")
    assert len(refs) == 1


def test_date_after_book_is_not_a_reference():
    refs = extract_references("Sunday Service Mark 12/3/2023 Mark 4:35-41")
    assert [r.display for r in refs] == ["Mark 4:35-41"]


def test_book_slug():
    assert book_slug("1 Corinthians") == "1-corinthians"
    assert book_slug("Song of Solomon") == "song-of-solomon"


def test_books_named_in_series_titles():
    assert books_named("Jude / 2 John / 3 John / Philemon (January–June 2023)") == \
        ["Philemon", "2 John", "3 John", "Jude"]  # canonical order
    assert books_named("Galatians (Fall 2023 · Spring 2024)") == ["Galatians"]
    assert books_named("1 Peter (Spring 2022)") == ["1 Peter"]
    assert books_named("Genesis 25–36 (Fall 2026)") == ["Genesis"]
    assert books_named("Hermeneutics (Spring 2025)") == []
    assert books_named("BCC Tenfold Covenant (2019–2020)") == []


def test_asr_period_verse_separator():
    assert [r.display for r in extract_references("as it says in James 2.19. I knew")] == ["James 2:19"]
    assert [r.display for r in extract_references("Read Romans 8. Then pray.")] == ["Romans 8"]


def test_chapter_validation_repairs_missing_colons():
    displays = lambda text: [r.display for r in extract_references(text)]
    assert displays("Romans 828 says all things") == ["Romans 8:28"]
    assert displays("Romans 519, and Romans 38") == ["Romans 5:19", "Romans 3:8"]  # only valid splits
    assert displays("Romans 124 is ambiguous") == []  # 1:24 or 12:4
    assert displays("Jude 24 and Jude 1:25 and Philemon 1") == ["Jude 1:24", "Jude 1:25", "Philemon 1"]
    assert displays("Psalm 119:105 and Psalm 150") == ["Psalms 119:105", "Psalms 150"]
    assert displays("Revelation 23") == ["Revelation 2:3"]
    assert displays("Titus 45") == []  # neither 45 nor 4:5 exists in Titus


def test_find_references_gives_spans_and_skips_invalid():
    text = "Read Rom. 8:1, not Titus 45, then Romans 828."
    matches = list(find_references(text))
    assert [m.reference.display for m in matches] == ["Romans 8:1", "Romans 8:28"]
    assert [text[m.start:m.end] for m in matches] == ["Rom. 8:1", "Romans 828"]
    assert matches[0].text == "Rom. 8:1"


def test_extract_references_dedupes_in_first_seen_order():
    assert [r.display for r in extract_references("John 3:16, Romans 8, John 3:16")] == \
        ["John 3:16", "Romans 8"]
