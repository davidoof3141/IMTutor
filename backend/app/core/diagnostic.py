"""Per-chapter rapid diagnostic: data model, YAML loading, and scoring.

Runs once per (sub)chapter BEFORE instruction. The score is a pure table
lookup -- (correct_count, experience) -> prior-knowledge level -- with no model
inference. The resulting level replaces the onboarding seed for that chapter's
`derive()` call only (see mapping.derive); it never updates the seed, and
nothing said during instruction feeds back (DR1).

The items and the scoring table are SME-authored data, not code:
`backend/content/<course>/<chapter>/diagnostic.yaml` (and, for a subchapter
with its own diagnostic, `<chapter>/<section>/diagnostic.yaml`). `load_*`
does file I/O once at startup; `lookup_level` and `score` touch nothing.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import get_args

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from app.core.profile import PriorKnowledge

COURSE = "informationsmanagement"
MIN_ITEMS = 3
MAX_ITEMS = 4
# The experience column of the scoring table. A chapter without its own
# experience item uses the onboarding seed here.
EXPERIENCE_LEVELS: tuple[PriorKnowledge, ...] = get_args(PriorKnowledge)


class DiagnosticOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    correct: bool = False
    # The explicit "I don't know" option; always scores 0.
    dont_know: bool = False


class DiagnosticItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    stem: str
    options: tuple[DiagnosticOption, ...]

    @model_validator(mode="after")
    def _check(self) -> "DiagnosticItem":
        if sum(o.correct for o in self.options) != 1:
            raise ValueError(f"item {self.stem!r} needs exactly one correct option")
        dont_know = [o for o in self.options if o.dont_know]
        if len(dont_know) != 1:
            raise ValueError(f"item {self.stem!r} needs exactly one 'I don't know' option")
        if dont_know[0].correct:
            raise ValueError(f"item {self.stem!r}: the 'I don't know' option must score 0")
        if len(self.options) < 3:
            raise ValueError(f"item {self.stem!r} needs at least two real options")
        return self


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str  # "3" (chapter) or "3.1" (subchapter)
    items: tuple[DiagnosticItem, ...]
    # experience (seed) level -> correct_count -> resulting chapter level
    scoring_table: dict[PriorKnowledge, dict[int, PriorKnowledge]]

    @model_validator(mode="after")
    def _check(self) -> "Diagnostic":
        if not MIN_ITEMS <= len(self.items) <= MAX_ITEMS:
            raise ValueError(f"diagnostic {self.key} needs {MIN_ITEMS}-{MAX_ITEMS} items")
        # Totality: every (correct_count, experience) cell is present.
        for experience in EXPERIENCE_LEVELS:
            row = self.scoring_table.get(experience, {})
            for count in range(len(self.items) + 1):
                if count not in row:
                    raise ValueError(
                        f"diagnostic {self.key}: scoring_table lacks "
                        f"experience={experience}, correct_count={count}"
                    )
        return self


def lookup_level(
    diagnostic: Diagnostic, correct_count: int, experience: PriorKnowledge
) -> PriorKnowledge:
    """The documented level for one scoring-table cell. Pure lookup."""
    return diagnostic.scoring_table[experience][correct_count]


def correct_count(diagnostic: Diagnostic, answers: Sequence[int]) -> int:
    """Number of items answered correctly. `answers[i]` is the chosen option
    index of item i; "I don't know" (and anything else wrong) scores 0."""
    if len(answers) != len(diagnostic.items):
        raise ValueError(f"expected {len(diagnostic.items)} answers, got {len(answers)}")
    total = 0
    for item, choice in zip(diagnostic.items, answers, strict=True):
        if not 0 <= choice < len(item.options):
            raise ValueError(f"option index {choice} out of range")
        total += item.options[choice].correct
    return total


def score(
    diagnostic: Diagnostic, answers: Sequence[int], experience: PriorKnowledge
) -> tuple[int, PriorKnowledge]:
    """(correct_count, chapter-level prior knowledge). `experience` is the
    onboarding seed; it is read, never written."""
    count = correct_count(diagnostic, answers)
    return count, lookup_level(diagnostic, count, experience)


def load_diagnostic(path: Path, key: str) -> Diagnostic:
    raw = yaml.safe_load(path.read_text())
    table = {
        experience: {int(count): level for count, level in row.items()}
        for experience, row in raw["scoring_table"].items()
    }
    return Diagnostic(
        key=key,
        items=tuple(
            DiagnosticItem(
                stem=item["stem"],
                options=tuple(DiagnosticOption(**opt) for opt in item["options"]),
            )
            for item in raw["items"]
        ),
        scoring_table=table,
    )


def load_diagnostics(content_dir: Path, course: str = COURSE) -> dict[str, Diagnostic]:
    """All diagnostics of one course, keyed "3" / "3.1". Missing directory = none."""
    root = content_dir / course
    found: dict[str, Diagnostic] = {}
    for path in sorted(root.glob("*/diagnostic.yaml")) + sorted(root.glob("*/*/diagnostic.yaml")):
        key = path.parent.name
        found[key] = load_diagnostic(path, key)
    return found


def resolve_diagnostic(
    diagnostics: dict[str, Diagnostic], chapter_number: str, section_number: str | None
) -> Diagnostic | None:
    """A subchapter's own diagnostic if it has one, else its chapter's."""
    if section_number is not None and section_number in diagnostics:
        return diagnostics[section_number]
    return diagnostics.get(chapter_number)
