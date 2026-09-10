"""Pre-generates the chapter/section welcome messages -- and the three starter
questions -- the tutor shows in training mode before the learner has said
anything (app/api/chapter_intro.py).

One fixed text plus three fixed starter questions per chapter and per section
-- deliberately not personalized per learner: instant and free to serve, and
reproducible, at the cost of not following any particular learner's
configured style for this one message. Uses the ruleset's *default* vector
(no rule fired, no override applied) as a neutral baseline for tone.

Unlike build_book_index.py / extract_book_images.py, this one makes real LLM
calls -- it needs OPENROUTER_API_KEY set, and costs time and tokens. Run it
once, and again after the book, the curriculum, or clauses.v1.yaml's wording
changes:

    uv run python scripts/generate_chapter_intros.py

Pass --starters-only to keep the existing intro texts and regenerate just the
starter questions (half the calls):

    uv run python scripts/generate_chapter_intros.py --starters-only
"""

import argparse
import json
import re
from pathlib import Path

from dotenv import load_dotenv

from app.api.chapter_intro import (
    INTRO_INSTRUCTION,
    INTRO_TRIGGER_MESSAGE,
    STARTER_QUESTION_COUNT,
    STARTERS_INSTRUCTION,
    STARTERS_TRIGGER_MESSAGE,
)
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


_LEADING_MARKER = re.compile(r"^\s*(?:\d+[.)]\s*|[-*•]\s*)+")


def _parse_starters(raw: str) -> list[str]:
    """One question per line. Strips stray numbering/bullets the model adds
    despite the instruction, then keeps only lines that end in "?" -- that
    drops any preamble ("Hier sind drei Fragen:") or intro prose the model
    returns instead of questions. Trimmed to STARTER_QUESTION_COUNT."""
    questions = [
        cleaned
        for line in raw.splitlines()
        if (cleaned := _LEADING_MARKER.sub("", line).strip()).endswith("?")
    ]
    return questions[:STARTER_QUESTION_COUNT]


def _existing_texts() -> dict[str, str]:
    """{key: intro text} from the current manifest -- bare-string (legacy) and
    {text, ...} entries alike. Used by --starters-only to skip the intro pass."""
    if not DEFAULT_CHAPTER_INTROS_PATH.exists():
        return {}
    raw: dict[str, object] = json.loads(DEFAULT_CHAPTER_INTROS_PATH.read_text())
    texts: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            texts[key] = value
        elif isinstance(value, dict):
            texts[key] = str(value.get("text", ""))
    return texts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate chapter/section intros + starters.")
    parser.add_argument(
        "--starters-only",
        action="store_true",
        help="Keep existing intro texts, regenerate only the starter questions.",
    )
    args = parser.parse_args()

    load_dotenv()
    assert_configured()

    ruleset = load_ruleset(RULES_DIR / "ruleset.v1.yaml")
    catalogue = load_catalogue(RULES_DIR / f"clauses.{ruleset.version}.yaml")
    system_prompt = assemble(ControlVector.model_validate(ruleset.defaults), catalogue)

    curriculum = extract_curriculum(BOOK_PATH)
    selections = _selections(curriculum)
    existing_texts = _existing_texts() if args.starters_only else {}

    intros: dict[str, dict[str, object]] = {}
    thin = 0
    for i, (chapter, section) in enumerate(selections, start=1):
        focus = format_focus(chapter, section)
        overview = format_overview(curriculum, chapter.number)
        query = chapter.title if section is None else f"{chapter.title} {section.title}"
        retrieved_context = format_context(retrieve(query))
        shared_context = "\n\n".join(
            part for part in (focus, overview, retrieved_context) if part
        )
        key = intro_key(chapter.number, section.number if section else None)

        text = existing_texts.get(key)
        if not text:
            text = complete_turn(
                system_prompt=system_prompt,
                user_message=INTRO_TRIGGER_MESSAGE,
                book_context=f"{shared_context}\n\n{INTRO_INSTRUCTION}",
            ).text
        starters = complete_turn(
            system_prompt=system_prompt,
            user_message=STARTERS_TRIGGER_MESSAGE,
            book_context=f"{shared_context}\n\n{STARTERS_INSTRUCTION}",
        )
        parsed = _parse_starters(starters.text)
        if len(parsed) < STARTER_QUESTION_COUNT:
            thin += 1
        intros[key] = {"text": text, "starters": parsed}
        print(f"  generated {i}/{len(selections)}: {key} ({len(parsed)} Fragen)      ", end="\r")

    DEFAULT_CHAPTER_INTROS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CHAPTER_INTROS_PATH.write_text(json.dumps(intros, ensure_ascii=False, indent=2))
    print(f"\nGenerated {len(intros)} chapter/section intros into {DEFAULT_CHAPTER_INTROS_PATH}")
    if thin:
        print(f"  warning: {thin} selection(s) got fewer than {STARTER_QUESTION_COUNT} starters")


if __name__ == "__main__":
    main()
