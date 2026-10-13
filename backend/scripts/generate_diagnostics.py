"""Generates the per-chapter rapid diagnostics (Kalyuga & Sweller 2004) as
static YAML files for a human to review, edit and commit.

OFFLINE and one-off: the server never generates diagnostics at request time
and never writes these files; it only loads and validates them at startup.
Needs OPENROUTER_API_KEY (real LLM calls) and the Postgres book index
(`scripts/build_book_index.py`). Prefer `make diagnostics` (see Makefile):

    uv run python scripts/generate_diagnostics.py                 # all chapters, skip unchanged
    uv run python scripts/generate_diagnostics.py --chapter 4     # one chapter
    uv run python scripts/generate_diagnostics.py --force         # even if source_hash matches
    uv run python scripts/generate_diagnostics.py --stale         # list drifted chapters, no LLM

Per chapter: read the chapter's chunks from Postgres, concatenate and
sha256-hash them; skip when the existing YAML's source_hash matches; else ask
the LLM for the four items, validate, write. Nothing is written to the database.
"""

import argparse
import json
import os
import random
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from app.core.diagnostic import (
    COURSE,
    DONT_KNOW_TEXT,
    ITEM_IDS,
    Diagnostic,
    DiagnosticFileError,
    load_diagnostic,
    parse_diagnostic,
)
from app.rag.chapter_text import chapter_text, source_hash
from app.rag.chunking import BOOK_PATH
from app.rag.toc import Chapter, extract_curriculum
from app.store.db import Conn

DIAGNOSTICS_DIR = Path(__file__).resolve().parents[1] / "content" / "diagnostics"
# Refuse (rather than silently truncate) a chapter too long for one prompt:
# the diagnostic must only cover text the model actually saw.
DEFAULT_MAX_CHARS = 350_000
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = f"""\
Du erstellst einen Kurztest zur Erfassung des Vorwissens vor einem Kapitel \
eines Lehrbuchs, nach dem Rapid-Diagnostic-Ansatz von Kalyuga und Sweller (2004). \
Du bekommst den Text EINES Kapitels. Stütze dich ausschließlich auf diesen Text; \
erfinde keine Fakten, die nicht darin stehen. Schreibe alles auf Deutsch.

Erstelle GENAU 4 Aufgaben, genau eine je Stufe, in dieser Reihenfolge:
1. recognition: Erkenne ein Kernkonzept. Frage z. B., welcher von drei genannten Begriffen \
oder Beispielen zu einem bestimmten Kernkonzept des Kapitels gehört. KEINE Ja/Nein-Frage.
2. classification: Eine kurze Situation; wähle, zu welchem von mehreren verwandten \
Konzepten des Kapitels sie gehört.
3. first_step: Ein kurzes Problem; was ist der ERSTE Schritt? Die richtige Antwort ist der \
strukturelle Schritt gemäß dem Kapitel; die falschen Antworten sind naheliegende \
Oberflächenhandlungen.
4. transfer: Ein Fall in einem Absatz, in einem leicht neuen Umfeld; die richtige Antwort \
erfordert das Schema des Kapitels.

Regeln je Aufgabe:
- Der Aufgabentext hat höchstens etwa 40 Wörter (bei transfer: ein Absatz), keine \
Verneinungen, keine Fangformulierungen.
- Genau DREI plausible Antwortoptionen, davon genau eine richtig. Die Optionen sind \
verschieden. Füge KEINE Option „{DONT_KNOW_TEXT}" hinzu; sie wird automatisch ergänzt.
- Die richtige Option steht nicht auffällig länger oder genauer da als die anderen.
- Alle drei Optionen sind inhaltlich konkrete Begriffe, Konzepte oder Schritte aus dem \
Themenfeld des Kapitels; die falschen Optionen sind plausible Verwechslungen, nie \
Füllwörter wie „Vielleicht" oder „Nein".
- Jede Aufgabe ist aus dem Kapiteltext beantwortbar; die Begriffe stammen aus dem Text.

Antworte NUR mit JSON, ohne Erklärungen, in genau dieser Form:
{{"items": [{{"level": "recognition", "stem": "...", "options": [{{"text": "...", \
"correct": true}}, {{"text": "..."}}, {{"text": "..."}}]}}, ... insgesamt 4 Einträge]}}
"""

# (system_prompt, chapter_text, model) -> (raw model text, model id actually used)
LLM = Callable[[str, str, str], tuple[str, str]]


class GenerationError(RuntimeError):
    pass


def openrouter_llm(system_prompt: str, text: str, model: str) -> tuple[str, str]:
    from app.llm.client import assert_configured, complete_turn

    assert_configured()
    response = complete_turn(
        system_prompt=system_prompt,
        user_message="Hier ist der Text des Kapitels:\n\n" + text,
        model=model,
        temperature=0.2,
    )
    return response.text, response.model


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parse_model_json(raw: str) -> list[dict[str, Any]]:
    data = json.loads(_FENCE.sub("", raw.strip()))
    items = data["items"] if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise TypeError("'items' must be a list")
    return items


def build_items(raw_items: list[dict[str, Any]], *, chapter_id: str) -> list[dict[str, Any]]:
    """Model output -> file items: ids q1-q4, the three plausible options in a
    reproducible shuffle (so the correct answer is not always first), and the
    fixed "I don't know" option appended last."""
    items = []
    for index, raw in enumerate(raw_items):
        options = [
            {"text": str(o["text"]).strip(), **({"correct": True} if o.get("correct") else {})}
            for o in raw.get("options", [])
        ]
        random.Random(f"{chapter_id}:{index}").shuffle(options)
        options.append({"text": DONT_KNOW_TEXT})
        items.append(
            {
                "id": ITEM_IDS[index] if index < len(ITEM_IDS) else f"q{index + 1}",
                "level": raw.get("level"),
                "stem": str(raw.get("stem", "")).strip(),
                "options": options,
            }
        )
    return items


def generate_diagnostic(
    *, chapter: Chapter, course_id: str, text: str, model: str, llm: LLM
) -> Diagnostic:
    """Calls the LLM (retrying on invalid output) and returns a validated Diagnostic."""
    problem = ""
    for _ in range(MAX_ATTEMPTS):
        raw, used_model = llm(SYSTEM_PROMPT, text, model)
        try:
            items = build_items(parse_model_json(raw), chapter_id=chapter.number)
            return parse_diagnostic(
                {
                    "chapter_id": chapter.number,
                    "course_id": course_id,
                    "source_hash": source_hash(text),
                    "generator_model": used_model,
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "items": items,
                }
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            problem = str(exc)
    raise GenerationError(
        f"chapter {chapter.number}: no valid diagnostic after {MAX_ATTEMPTS} attempts "
        f"(last problem: {problem})"
    )


def to_yaml(diagnostic: Diagnostic) -> str:
    def item(i: Any) -> dict[str, Any]:
        return {
            "id": i.id,
            "level": i.level,
            "stem": i.stem,
            "options": [
                {"text": o.text, "correct": True} if o.correct else {"text": o.text}
                for o in i.options
            ],
        }

    payload = {
        "chapter_id": diagnostic.chapter_id,
        "course_id": diagnostic.course_id,
        "source_hash": diagnostic.source_hash,
        "generator_model": diagnostic.generator_model,
        "generated_at": diagnostic.generated_at,
        "items": [item(i) for i in diagnostic.items],
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)


def existing_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return load_diagnostic(path).source_hash
    except DiagnosticFileError:
        return None  # an invalid file is regenerated, not trusted


def process_chapter(
    *,
    chapter: Chapter,
    text: str,
    out_dir: Path,
    course_id: str,
    model: str,
    llm: LLM,
    force: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Returns "skipped", "written" or "empty". Idempotent: an existing file
    whose source_hash matches the chapter text is left untouched (no LLM call)
    unless `force`."""
    if not text:
        return "empty"
    path = out_dir / course_id / f"{chapter.number}.yaml"
    if not force and existing_hash(path) == source_hash(text):
        return "skipped"
    if len(text) > max_chars:
        raise GenerationError(
            f"chapter {chapter.number} has {len(text)} characters (limit {max_chars}); "
            "raise --max-chars or split the chapter -- not truncating silently"
        )
    diagnostic = generate_diagnostic(
        chapter=chapter, course_id=course_id, text=text, model=model, llm=llm
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_yaml(diagnostic))
    return "written"


def list_stale(
    *, curriculum: list[Chapter], conn: Conn, out_dir: Path, course_id: str
) -> list[tuple[str, str]]:
    """(chapter number, reason) for chapters whose diagnostic is missing or whose hash drifted."""
    rows = []
    for chapter in curriculum:
        text = chapter_text(conn, chapter)
        if not text:
            continue
        stored = existing_hash(out_dir / course_id / f"{chapter.number}.yaml")
        if stored is None:
            rows.append((chapter.number, "missing"))
        elif stored != source_hash(text):
            rows.append((chapter.number, "stale"))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--chapter", help="only this chapter number")
    parser.add_argument("--force", action="store_true", help="regenerate even if unchanged")
    parser.add_argument("--stale", action="store_true", help="list drifted chapters and exit")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--out-dir", type=Path, default=DIAGNOSTICS_DIR)
    args = parser.parse_args(argv)

    load_dotenv()
    from app.store import db

    curriculum = extract_curriculum(BOOK_PATH)
    if args.chapter:
        curriculum = [c for c in curriculum if c.number == args.chapter]
        if not curriculum:
            print(f"unknown chapter: {args.chapter}", file=sys.stderr)
            return 2
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    with db.connection() as conn:
        if args.stale:
            rows = list_stale(
                curriculum=curriculum, conn=conn, out_dir=args.out_dir, course_id=COURSE
            )
            for number, reason in rows:
                print(f"{number}\t{reason}")
            if not rows:
                print("all diagnostics match the book index")
            return 0
        failed = 0
        for chapter in curriculum:
            try:
                result = process_chapter(
                    chapter=chapter,
                    text=chapter_text(conn, chapter),
                    out_dir=args.out_dir,
                    course_id=COURSE,
                    model=model,
                    llm=openrouter_llm,
                    force=args.force,
                    max_chars=args.max_chars,
                )
            except GenerationError as exc:
                failed += 1
                print(f"FAILED  {exc}", file=sys.stderr)
                continue
            print(f"{result:8}chapter {chapter.number}: {chapter.title}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
