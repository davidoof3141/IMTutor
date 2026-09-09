from app.rag.toc import find_chapter, format_focus, format_overview, parse_chapters

ENTRIES = [
    ("Vorwort zur 6. Auflage", 5),
    ("Inhaltsverzeichnis", 9),
    ("1 Einleitung", 25),
    ("1.1 Zur Bedeutung des Informationsmanagements", 25),
    ("1.2 Ziel des Buches", 28),
    ("Literatur", 32),
    ("Teil I Grundlagen", 33),
    ("2 Begriffe und Definitionen", 34),
    ("2.1 Syntax, Daten, Information, Wissen", 34),
    ("2.2 Informationstechnik und -technologie", 43),
    ("Literatur", 49),
    ("3 Modellierung", 53),
    ("Weiterführende Literatur", 799),
    ("Sachverzeichnis", 801),
]


def test_only_numbered_chapters_and_sections_survive() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    assert [c.number for c in chapters] == ["1", "2", "3"]


def test_front_and_back_matter_and_part_headings_are_skipped() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    titles = [c.title for c in chapters]
    assert "Vorwort zur 6. Auflage" not in titles
    assert "Teil I Grundlagen" not in titles
    assert "Weiterführende Literatur" not in titles
    assert "Sachverzeichnis" not in titles


def test_literatur_entries_are_not_treated_as_sections() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    ch2 = next(c for c in chapters if c.number == "2")
    assert [s.number for s in ch2.sections] == ["2.1", "2.2"]


def test_chapter_and_section_titles_and_page_starts() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    ch1 = chapters[0]
    assert ch1.title == "Einleitung"
    assert ch1.page_start == 25
    assert [s.number for s in ch1.sections] == ["1.1", "1.2"]
    assert ch1.sections[0].title == "Zur Bedeutung des Informationsmanagements"


def test_page_end_is_next_starts_page_minus_one() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    ch1 = chapters[0]
    # chapter 1 ends the page before chapter 2 starts (page 34), even though
    # "Teil I Grundlagen" and "Literatur" sit between them in the outline
    assert ch1.page_end == 33
    # section 1.1 ends the page before section 1.2 starts
    assert ch1.sections[0].page_end == 27
    # last section in a chapter ends where the chapter ends
    assert ch1.sections[-1].page_end == ch1.page_end


def test_last_chapter_page_end_falls_back_to_last_page() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    ch3 = chapters[-1]
    assert ch3.number == "3"
    assert ch3.page_end == 814


def test_stray_section_without_matching_chapter_is_skipped() -> None:
    entries = [("9.1 Orphan section", 10), ("1 Real Chapter", 20)]
    chapters = parse_chapters(entries, last_page=100)
    assert [c.number for c in chapters] == ["1"]
    assert chapters[0].sections == []


def test_find_chapter() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    assert find_chapter(chapters, "2") is not None
    assert find_chapter(chapters, "2").title == "Begriffe und Definitionen"
    assert find_chapter(chapters, "99") is None


def test_format_focus_names_chapter_and_optional_section() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    ch2 = find_chapter(chapters, "2")
    assert ch2 is not None

    focus_no_section = format_focus(ch2, None)
    assert "Kapitel 2: Begriffe und Definitionen" in focus_no_section
    assert "Abschnitt" not in focus_no_section

    focus_with_section = format_focus(ch2, ch2.sections[0])
    assert "Kapitel 2: Begriffe und Definitionen" in focus_with_section
    assert "Abschnitt 2.1: Syntax, Daten, Information, Wissen" in focus_with_section


def test_format_overview_lists_every_chapter_and_marks_the_current_one() -> None:
    chapters = parse_chapters(ENTRIES, last_page=814)
    overview = format_overview(chapters, "2")
    assert "1. Einleitung" in overview
    assert "2. Begriffe und Definitionen <- aktuelles Kapitel" in overview
    assert "3. Modellierung" in overview
    assert overview.count("<- aktuelles Kapitel") == 1
