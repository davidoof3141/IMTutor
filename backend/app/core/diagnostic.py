"""Per-chapter rapid diagnostic (Kalyuga & Sweller 2004): data model, YAML
loading, validation and scoring.

Runs once per chapter BEFORE instruction. The score is a pure table lookup --
(correct_count, seed) -> chapter-level prior knowledge -- with no model
inference. The resulting level replaces the onboarding seed for that chapter's
`derive()` call only (see mapping.derive); it never updates the seed, and
nothing said during instruction feeds back (DR1).

The items are generated OFFLINE by scripts/generate_diagnostics.py, reviewed
by a human and committed as static YAML:

    backend/content/diagnostics/<course_id>/<chapter_id>.yaml
    backend/content/diagnostics/scoring_table.yaml     (shared)

The server only ever READS these files, at startup. `load_*` does file I/O
once there; `lookup_level` and `score` touch nothing.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.core.profile import PriorKnowledge

COURSE = "informationsmanagement"
SCORING_TABLE_FILENAME = "scoring_table.yaml"

Level = Literal["recognition", "classification", "first_step", "transfer"]
# Fixed order: one item per level, in this order.
LEVELS: tuple[Level, ...] = get_args(Level)
ITEM_IDS = ("q1", "q2", "q3", "q4")
OPTIONS_PER_ITEM = 4
# The sentinel text of the explicit "I don't know" option (always scores 0).
# The UI shows a localized label for it; the file keeps this exact string.
DONT_KNOW_TEXT = "I don't know"
SEEDS: tuple[PriorKnowledge, ...] = get_args(PriorKnowledge)


class DiagnosticFileError(ValueError):
    """A diagnostic or scoring-table file failed validation. Names the file."""

    def __init__(self, path: Path, problem: str) -> None:
        super().__init__(f"{path}: {problem}")
        self.path = path
        self.problem = problem


class DiagnosticOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    correct: bool = False

    @property
    def dont_know(self) -> bool:
        return self.text == DONT_KNOW_TEXT


class DiagnosticItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    level: Level
    stem: str
    options: tuple[DiagnosticOption, ...]

    @model_validator(mode="after")
    def _check(self) -> "DiagnosticItem":
        if not self.stem.strip():
            raise ValueError(f"item {self.id}: empty stem")
        if len(self.options) != OPTIONS_PER_ITEM:
            raise ValueError(
                f"item {self.id}: needs exactly {OPTIONS_PER_ITEM} options, "
                f"got {len(self.options)}"
            )
        if any(not o.text.strip() for o in self.options):
            raise ValueError(f"item {self.id}: empty option text")
        texts = [o.text.strip().casefold() for o in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError(f"item {self.id}: options are not distinct")
        if sum(o.correct for o in self.options) != 1:
            raise ValueError(f"item {self.id}: needs exactly one correct option")
        dont_know = [o for o in self.options if o.dont_know]
        if len(dont_know) != 1:
            raise ValueError(f"item {self.id}: needs exactly one {DONT_KNOW_TEXT!r} option")
        if dont_know[0].correct:
            raise ValueError(f"item {self.id}: the {DONT_KNOW_TEXT!r} option must score 0")
        return self


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    chapter_id: str
    course_id: str
    source_hash: str  # sha256 of the chapter's concatenated chunks at generation time
    generator_model: str
    generated_at: str  # ISO timestamp
    items: tuple[DiagnosticItem, ...]

    @model_validator(mode="after")
    def _check(self) -> "Diagnostic":
        if not self.chapter_id.strip() or not self.course_id.strip():
            raise ValueError("chapter_id and course_id are required")
        if not self.source_hash:
            raise ValueError("source_hash is required")
        if [i.level for i in self.items] != list(LEVELS):
            raise ValueError(
                f"items must be exactly one per level in the order {', '.join(LEVELS)}; "
                f"got {[i.level for i in self.items]}"
            )
        if [i.id for i in self.items] != list(ITEM_IDS):
            raise ValueError(f"item ids must be {', '.join(ITEM_IDS)}")
        return self


class ScoringRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    correct: int
    seed: tuple[PriorKnowledge, ...]
    level: PriorKnowledge


class ScoringTable(BaseModel):
    """(correct_count, seed) -> chapter-level prior knowledge. Total over
    0..len(LEVELS) correct x every seed, each pair resolved exactly once."""

    model_config = ConfigDict(frozen=True)

    table: tuple[ScoringRow, ...]

    @model_validator(mode="after")
    def _check(self) -> "ScoringTable":
        seen: set[tuple[int, str]] = set()
        for row in self.table:
            if not 0 <= row.correct <= len(LEVELS):
                raise ValueError(f"correct={row.correct} is out of range 0..{len(LEVELS)}")
            for seed in row.seed:
                if (row.correct, seed) in seen:
                    raise ValueError(f"(correct={row.correct}, seed={seed}) is listed twice")
                seen.add((row.correct, seed))
        missing = [
            f"(correct={c}, seed={s})"
            for c in range(len(LEVELS) + 1)
            for s in SEEDS
            if (c, s) not in seen
        ]
        if missing:
            raise ValueError(f"scoring table does not resolve: {', '.join(missing)}")
        return self

    def lookup(self, correct_count: int, seed: PriorKnowledge) -> PriorKnowledge:
        for row in self.table:
            if row.correct == correct_count and seed in row.seed:
                return row.level
        raise KeyError((correct_count, seed))  # unreachable: validated total


def lookup_level(table: ScoringTable, correct_count: int, seed: PriorKnowledge) -> PriorKnowledge:
    """The documented level for one scoring-table cell. Pure lookup."""
    return table.lookup(correct_count, seed)


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
    diagnostic: Diagnostic,
    answers: Sequence[int],
    seed: PriorKnowledge,
    table: ScoringTable,
) -> tuple[int, PriorKnowledge]:
    """(correct_count, chapter-level prior knowledge). `seed` is the onboarding
    prior_knowledge_seed; it is read, never written."""
    count = correct_count(diagnostic, answers)
    return count, lookup_level(table, count, seed)


def parse_diagnostic(raw: Mapping[str, Any]) -> Diagnostic:
    """Validates a diagnostic mapping (as read from YAML or returned by the
    generator). Raises pydantic.ValidationError / ValueError."""
    return Diagnostic.model_validate(dict(raw))


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise DiagnosticFileError(path, f"cannot be read as YAML: {exc}") from exc


def _describe(exc: ValidationError | ValueError) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}" for e in exc.errors()
        )
    return str(exc)


def load_scoring_table(path: Path) -> ScoringTable:
    raw = _read_yaml(path)
    try:
        return ScoringTable.model_validate(raw)
    except (ValidationError, ValueError, TypeError) as exc:
        raise DiagnosticFileError(path, _describe(exc)) from exc  # type: ignore[arg-type]


def load_diagnostic(path: Path) -> Diagnostic:
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        raise DiagnosticFileError(path, "top level must be a mapping")
    try:
        diagnostic = parse_diagnostic(raw)
    except (ValidationError, ValueError) as exc:
        raise DiagnosticFileError(path, _describe(exc)) from exc
    if str(diagnostic.chapter_id) != path.stem:
        raise DiagnosticFileError(
            path, f"chapter_id {diagnostic.chapter_id!r} does not match the file name"
        )
    if diagnostic.course_id != path.parent.name:
        raise DiagnosticFileError(
            path, f"course_id {diagnostic.course_id!r} does not match the directory"
        )
    return diagnostic


def diagnostics_dir_paths(root: Path, course: str = COURSE) -> list[Path]:
    return sorted((root / course).glob("*.yaml"))


def load_diagnostics(root: Path, course: str = COURSE) -> dict[str, Diagnostic]:
    """All of one course's diagnostics, keyed by chapter_id. A missing course
    directory means none. Raises DiagnosticFileError on the first invalid file."""
    found: dict[str, Diagnostic] = {}
    for path in diagnostics_dir_paths(root, course):
        diagnostic = load_diagnostic(path)
        found[diagnostic.chapter_id] = diagnostic
    return found


def stale_chapters(
    diagnostics: Mapping[str, Diagnostic], current_hashes: Mapping[str, str]
) -> list[str]:
    """Chapter ids whose YAML `source_hash` differs from the chapter's current
    content hash. Chapters without a current hash (not in the database) are
    not reported."""
    return sorted(
        chapter_id
        for chapter_id, diagnostic in diagnostics.items()
        if chapter_id in current_hashes and current_hashes[chapter_id] != diagnostic.source_hash
    )


def resolve_diagnostic(
    diagnostics: Mapping[str, Diagnostic], chapter_number: str
) -> Diagnostic | None:
    return diagnostics.get(chapter_number)
