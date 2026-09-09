"""The pure lesson planner.

Sits beside the control layer and consumes its output (`ControlVector`) plus
the curriculum, same purity requirements as mapping.py: no network, no
clock, no randomness, no file I/O at call time, no global state, no LLM
import -- directly or transitively. Enforced by tests/test_purity.py.

The plan does not change based on how the learner performs -- no
remediation, no skipping, no difficulty adjustment (invariant 6). Checkpoint
answers are ordinary turns, logged and otherwise ignored here.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from app.core.constants import ASSESSMENT_FREQUENCY, EXAMPLE_DENSITY, EXPLANATION_DEPTH, PACING
from app.core.vector import ADMISSIBLE_VALUES, ControlVector
from app.rag.toc import Chapter, Section, find_chapter

StepKind = Literal["explain", "example", "checkpoint", "recap"]
STEP_KINDS: tuple[StepKind, ...] = ("explain", "example", "checkpoint", "recap")

AssessmentPattern = Literal["each_section", "every_second_section", "none"]


class LessonStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    kind: StepKind
    section_ref: str  # "4.2", or "4" when the step covers a whole chapter
    page_start: int
    page_end: int


class CurriculumSelection(BaseModel):
    """What the learner picked in training mode -- see
    app/store/study_mode.py::StudyModeState, which is where this comes from
    at the API layer."""

    model_config = ConfigDict(frozen=True)

    chapter_number: str
    section_number: str | None = None


Curriculum = list[Chapter]

# step index -> the parameter (and its value) that caused that step to exist,
# e.g. "explanation_depth=4"; the one recap step attributes to "always".
# Same spirit as Attribution in the mapping layer (app/core/vector.py).
PlanRationale = dict[int, str]


class PlannerTable(BaseModel):
    """Loaded from rules/planner.v1.yaml. The numbers a lesson plan is built
    from are data, not code -- same reasoning as invariant 7 for the rule
    set. What the numbers *mean* (how a section count or a checkpoint
    pattern turns into steps) is plan_lesson()'s job, not this file's."""

    model_config = ConfigDict(frozen=True)

    version: str
    pacing_sections: dict[int, int]
    explain_per_section: dict[int, int]
    example_per_section: dict[int, int]
    assessment_pattern: dict[str, AssessmentPattern]


def load_planner_table(path: Path) -> PlannerTable:
    raw = yaml.safe_load(path.read_text())
    table = PlannerTable(
        version=raw["version"],
        pacing_sections=raw["pacing_sections"],
        explain_per_section=raw["explain_per_section"],
        example_per_section=raw["example_per_section"],
        assessment_pattern=raw["assessment_pattern"],
    )
    _check_table_totality(table)
    return table


def _check_table_totality(table: PlannerTable) -> None:
    missing: list[str] = []
    for value in ADMISSIBLE_VALUES[PACING]:
        if value not in table.pacing_sections:
            missing.append(f"pacing_sections[{value}]")
    for value in ADMISSIBLE_VALUES[EXPLANATION_DEPTH]:
        if value not in table.explain_per_section:
            missing.append(f"explain_per_section[{value}]")
    for value in ADMISSIBLE_VALUES[EXAMPLE_DENSITY]:
        if value not in table.example_per_section:
            missing.append(f"example_per_section[{value}]")
    for value in ADMISSIBLE_VALUES[ASSESSMENT_FREQUENCY]:
        if value not in table.assessment_pattern:
            missing.append(f"assessment_pattern[{value}]")
    if missing:
        raise ValueError(f"Planner table {table.version} is missing entries for: {missing}")


@dataclass(frozen=True)
class _Unit:
    """One section-equivalent the lesson covers: an actual X.Y section, or
    the whole chapter when it has none of its own."""

    ref: str
    page_start: int
    page_end: int


def _find_section(chapter: Chapter, section_number: str) -> Section | None:
    return next((s for s in chapter.sections if s.number == section_number), None)


def _resolve_units(
    vector: ControlVector,
    selection: CurriculumSelection,
    chapter: Chapter,
    table: PlannerTable,
) -> list[_Unit]:
    if selection.section_number is not None:
        section = _find_section(chapter, selection.section_number)
        if section is None:
            raise ValueError(f"unknown section: {selection.section_number}")
        return [_Unit(section.number, section.page_start, section.page_end)]

    if not chapter.sections:
        return [_Unit(chapter.number, chapter.page_start, chapter.page_end)]

    # Sections beyond the end of the chapter are not invented.
    count = min(table.pacing_sections[vector.pacing], len(chapter.sections))
    return [_Unit(s.number, s.page_start, s.page_end) for s in chapter.sections[:count]]


def plan_lesson(
    vector: ControlVector,
    selection: CurriculumSelection,
    curriculum: Curriculum,
    table: PlannerTable,
) -> tuple[list[LessonStep], PlanRationale]:
    """Pure, total, deterministic: same (vector, selection, curriculum,
    table) always returns the same steps and rationale. `lesson_id` and
    `created_at` are assigned by the caller, not here, so this stays
    clock-free and snapshot-testable.

    Raises ValueError for a chapter/section the curriculum doesn't have --
    callers validate the selection against the curriculum first (see
    app/api/study_mode.py's existing find_chapter check for the same
    pattern), so this is a defensive check, not the primary validation path.
    """
    chapter = find_chapter(list(curriculum), selection.chapter_number)
    if chapter is None:
        raise ValueError(f"unknown chapter: {selection.chapter_number}")

    units = _resolve_units(vector, selection, chapter, table)
    pattern = table.assessment_pattern[vector.assessment_frequency]

    steps: list[LessonStep] = []
    rationale: PlanRationale = {}

    def add(kind: StepKind, ref: str, page_start: int, page_end: int, cause: str) -> None:
        index = len(steps)
        steps.append(
            LessonStep(
                index=index,
                kind=kind,
                section_ref=ref,
                page_start=page_start,
                page_end=page_end,
            )
        )
        rationale[index] = cause

    explain_count = table.explain_per_section[vector.explanation_depth]
    example_count = table.example_per_section[vector.example_density]
    explain_cause = f"explanation_depth={vector.explanation_depth}"
    example_cause = f"example_density={vector.example_density}"
    checkpoint_cause = f"assessment_frequency={vector.assessment_frequency}"

    for position, unit in enumerate(units, start=1):
        for _ in range(explain_count):
            add("explain", unit.ref, unit.page_start, unit.page_end, explain_cause)
        for _ in range(example_count):
            add("example", unit.ref, unit.page_start, unit.page_end, example_cause)

        if pattern == "each_section":
            add("checkpoint", unit.ref, unit.page_start, unit.page_end, checkpoint_cause)
        elif pattern == "every_second_section":
            if position % 2 == 0:
                prev = units[position - 2]
                add("checkpoint", unit.ref, prev.page_start, unit.page_end, checkpoint_cause)
            elif position == len(units):
                # odd section count -- one trailing checkpoint for the last, unpaired section
                add("checkpoint", unit.ref, unit.page_start, unit.page_end, checkpoint_cause)
        # pattern == "none": no checkpoint steps

    overall_ref = chapter.number if len(units) > 1 else units[0].ref
    add("recap", overall_ref, units[0].page_start, units[-1].page_end, "always")

    return steps, rationale
