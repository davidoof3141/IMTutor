"""Pre-generates the chapter/section welcome messages the tutor shows in
training mode before the learner has said anything (app/api/chapter_intro.py).

One fixed text per chapter and per section -- deliberately not personalized
per learner: instant and free to serve, and reproducible, at the cost of not
following any particular learner's configured style for this one message.
Uses the ruleset's *default* vector (no rule fired, no override applied) as
a neutral baseline for tone.

Unlike build_book_index.py / extract_book_images.py, this one makes real LLM
calls -- it needs OPENROUTER_API_KEY set, and costs time and tokens. Run it
once, and again after the book, the curriculum, or clauses.v1.yaml's wording
changes:

    uv run python scripts/generate_chapter_intros.py
"""

import json
from pathlib import Path

from dotenv import load_dotenv

from app.api.chapter_intro import INTRO_INSTRUCTION, INTRO_TRIGGER_MESSAGE
from app.core.assembler import assemble
from app.core.clauses import load_catalogue
from app.core.rules import load_ruleset
from app.core.vector import ControlVector
from app.llm.client import assert_configured, complete_turn
from app.rag.chapter_intros import DEFAULT_CHAPTER_INTROS_PATH, intro_key
from app.rag.chunking import BOOK_PATH
from app.rag.retriever import format_context, retrieve
from app.rag.toc import Chapter, Section, extract_curriculum, format_focus, format_overview

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"


def _selections(curriculum: list[Chapter]) -> list[tuple[Chapter, Section | None]]:
    selections: list[tuple[Chapter, Section | None]] = []
    for chapter in curriculum:
        selections.append((chapter, None))
        selections.extend((chapter, section) for section in chapter.sections)
    return selections


def main() -> None:
    load_dotenv()
    assert_configured()

    ruleset = load_ruleset(RULES_DIR / "ruleset.v1.yaml")
    catalogue = load_catalogue(RULES_DIR / f"clauses.{ruleset.version}.yaml")
    system_prompt = assemble(ControlVector.model_validate(ruleset.defaults), catalogue)

    curriculum = extract_curriculum(BOOK_PATH)
    selections = _selections(curriculum)

    intros: dict[str, str] = {}
    for i, (chapter, section) in enumerate(selections, start=1):
        focus = format_focus(chapter, section)
        overview = format_overview(curriculum, chapter.number)
        query = chapter.title if section is None else f"{chapter.title} {section.title}"
        retrieved_context = format_context(retrieve(query))
        book_context = "\n\n".join(
            part for part in (focus, overview, retrieved_context, INTRO_INSTRUCTION) if part
        )

        response = complete_turn(
            system_prompt=system_prompt,
            user_message=INTRO_TRIGGER_MESSAGE,
            book_context=book_context,
        )
        key = intro_key(chapter.number, section.number if section else None)
        intros[key] = response.text
        print(f"  generated {i}/{len(selections)}: {key}", end="\r")

    DEFAULT_CHAPTER_INTROS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CHAPTER_INTROS_PATH.write_text(json.dumps(intros, ensure_ascii=False, indent=2))
    print(f"\nGenerated {len(intros)} chapter/section intros into {DEFAULT_CHAPTER_INTROS_PATH}")


if __name__ == "__main__":
    main()
