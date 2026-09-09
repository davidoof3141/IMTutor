"""Extracts a chapter/section curriculum from the book's own table of
contents (PDF outline/bookmarks), for the frontend's training-mode schedule.

Split the same way as chunking.py: PDF access (`flatten_outline`,
`extract_curriculum`) is separate from the pure, testable grouping logic
(`parse_chapters`).
"""

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader

_CHAPTER_RE = re.compile(r"^(\d+)\s+(?!\d)(.+)$")
_SECTION_RE = re.compile(r"^(\d+)\.(\d+)\s+(.+)$")


class Section(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: str  # e.g. "5.3"
    title: str
    page_start: int
    page_end: int


class Chapter(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: str  # e.g. "5"
    title: str
    page_start: int
    page_end: int
    sections: list[Section]


def flatten_outline(reader: PdfReader) -> list[tuple[str, int]]:
    """Flattens pypdf's nested outline (bookmark | nested list of children)
    into an ordered (title, 1-indexed page) sequence. Nesting depth is
    dropped -- chapter/section membership is recovered from title numbering
    in parse_chapters, not from outline structure (chapters aren't uniformly
    nested: some sit directly at the top level, others under a "Teil" part
    heading).
    """
    entries: list[tuple[str, int]] = []

    def walk(items: list[Any]) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                page_number = reader.get_destination_page_number(item)
                if page_number is not None:
                    entries.append((item.title, page_number + 1))

    walk(reader.outline)
    return entries


def parse_chapters(entries: list[tuple[str, int]], *, last_page: int) -> list[Chapter]:
    """Groups a flat (title, page) sequence into chapters and their sections
    by title numbering: "5 Foo" starts chapter 5, "5.3 Bar" is a section of
    the chapter currently in progress if its number matches. Anything else
    (front/back matter, "Teil" part headings, "Literatur") is skipped.
    """
    raw_chapters: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_title, page in entries:
        title = raw_title.strip()
        section_match = _SECTION_RE.match(title)
        chapter_match = _CHAPTER_RE.match(title)
        if section_match and current is not None and section_match.group(1) == current["number"]:
            current["sections"].append(
                {
                    "number": f"{section_match.group(1)}.{section_match.group(2)}",
                    "title": section_match.group(3),
                    "page_start": page,
                }
            )
        elif chapter_match:
            current = {
                "number": chapter_match.group(1),
                "title": chapter_match.group(2),
                "page_start": page,
                "sections": [],
            }
            raw_chapters.append(current)

    chapters: list[Chapter] = []
    for i, chapter in enumerate(raw_chapters):
        chapter_end = (
            raw_chapters[i + 1]["page_start"] - 1 if i + 1 < len(raw_chapters) else last_page
        )
        chapter_end = max(chapter_end, chapter["page_start"])
        sections: list[Section] = []
        raw_sections = chapter["sections"]
        for j, section in enumerate(raw_sections):
            section_end = (
                raw_sections[j + 1]["page_start"] - 1 if j + 1 < len(raw_sections) else chapter_end
            )
            sections.append(
                Section(
                    number=section["number"],
                    title=section["title"],
                    page_start=section["page_start"],
                    page_end=max(section_end, section["page_start"]),
                )
            )
        chapters.append(
            Chapter(
                number=chapter["number"],
                title=chapter["title"],
                page_start=chapter["page_start"],
                page_end=chapter_end,
                sections=sections,
            )
        )
    return chapters


def extract_curriculum(pdf_path: Path) -> list[Chapter]:
    reader = PdfReader(str(pdf_path))
    entries = flatten_outline(reader)
    return parse_chapters(entries, last_page=len(reader.pages))


def find_chapter(chapters: list[Chapter], number: str) -> Chapter | None:
    return next((c for c in chapters if c.number == number), None)


def format_focus(chapter: Chapter, section: Section | None) -> str:
    """Fixed-template sentence naming the learner's training-mode selection.
    Only the chapter/section names are substituted -- same spirit as
    retriever.py's format_context, kept out of core/assembler.py's pure
    clause-concatenation output.
    """
    where = f"Kapitel {chapter.number}: {chapter.title}"
    if section is not None:
        where += f", Abschnitt {section.number}: {section.title}"
    return (
        f"Die lernende Person hat den Lernmodus gewählt und beschäftigt sich "
        f"gerade mit {where} des Lehrbuchs. Orientiere dich an Einordnung und "
        "Terminologie dieses Kapitels, wenn es passt, beantworte aber auch "
        "Fragen, die davon abweichen."
    )


def format_overview(chapters: list[Chapter], current_chapter_number: str) -> str:
    """Fixed-template table of contents (chapter numbers and titles only,
    same as the frontend's curriculum panel already shows), the current
    chapter marked -- structural fact, not free text, same spirit as
    format_focus. Used to ground the "how does this fit into the whole
    book" part of the chapter-intro message (app/api/chapter_intro.py) in
    the book's real structure instead of the model inventing one.
    """
    lines = ["Gesamtaufbau des Lehrbuchs:"]
    for chapter in chapters:
        marker = " <- aktuelles Kapitel" if chapter.number == current_chapter_number else ""
        lines.append(f"{chapter.number}. {chapter.title}{marker}")
    return "\n".join(lines)
