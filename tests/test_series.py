from sermon_core import Paragraph, Sermon, extract_references, group_series

# A small rule set in the shape churches write in their YAML. Order matters:
# the first matching rule wins, include_ids override everything.
RULES = [
    {"slug": "prayer", "title": "Prayer meetings", "category": "Other events",
     "pattern": r"praise\s*(?:and|&)\s*prayer"},
    {"slug": "study-2026", "title": "Genesis (2026)", "category": "Bible studies",
     "pattern": r"bible study|\bgenesis\b", "start": "20260101", "end": "20261231"},
    {"slug": "sunday-luke", "title": "Luke", "category": "Sunday sermons", "book": "Luke",
     "exclude": "retreat", "current": True},
    {"slug": "other-sunday", "title": "Other Sunday messages", "category": "Sunday sermons",
     "pattern": "sunday", "include_ids": ["guest"]},
]


def message(id, title, date, text=""):
    return Sermon(id, title, date, None, "https://example.com/" + id, None,
                  [Paragraph(0, 60, text)], extract_references(title))


def assignments(messages):
    return {s.id: g.slug for g in group_series(messages, RULES) for s in g.sermons}


def test_first_matching_rule_wins_and_dates_bound_a_rule():
    rows = [message("prayer", "Praise and Prayer (Luke 22:39-46)", "20260613"),
            message("study", "Jacob's Dream (Genesis 28)", "20261008"),
            message("old-study", "Jacob's Dream (Genesis 28)", "20251008"),
            message("luke", "Sunday Service (Luke 18:1-8)", "20261001")]
    assert assignments(rows) == {"prayer": "prayer", "study": "study-2026", "luke": "sunday-luke"}


def test_book_rule_needs_the_title_book_or_an_explicit_introduction():
    rows = [message("intro", "Sunday Service", "20260202",
                    "Turn your Bibles with me to Luke chapter fifteen."),
            message("incidental", "Sunday Service", "20260202",
                    "In Romans chapter eight Paul also writes about this."),
            message("two-books", "Sunday Service (Luke 1:1; Acts 1:1)", "20260202")]
    assert assignments(rows) == {"intro": "sunday-luke", "incidental": "other-sunday",
                                 "two-books": "other-sunday"}


def test_include_ids_and_exclude_patterns():
    rows = [message("guest", "A Word for Drifters (Hebrews 6:1-6)", "20261102"),
            message("retreat", "Retreat Sunday (Luke 5:1)", "20260705")]
    assert assignments(rows) == {"guest": "other-sunday", "retreat": "other-sunday"}


def test_groups_keep_rule_order_and_sort_oldest_first():
    rows = [message("b", "Sunday (Luke 2:1)", "20260601"), message("a", "Sunday (Luke 1:1)", "20260501")]
    groups = group_series(rows, RULES)
    assert [g.slug for g in groups] == ["prayer", "study-2026", "sunday-luke", "other-sunday"]
    luke = groups[2]
    assert [s.id for s in luke.sermons] == ["a", "b"] and luke.current
