"""Guards against a planner-table edit that silently inverts a parameter's
effect -- e.g. a typo that makes a higher explanation_depth explain less.
"""

from app.core.constants import EXAMPLE_DENSITY, EXPLANATION_DEPTH, PACING
from app.core.planner import (
    Curriculum,
    CurriculumSelection,
    PlannerTable,
    plan_lesson,
)
from app.core.vector import ADMISSIBLE_VALUES, ControlVector


def _vector(**overrides: object) -> ControlVector:
    base: dict[str, object] = {
        "explanation_depth": 3,
        "example_density": 3,
        "concreteness": 3,
        "register": "neutral",
        "pacing": 2,
        "assessment_frequency": "every_second_topic",
    }
    base.update(overrides)
    return ControlVector.model_validate(base)


def _explain_count(steps: list) -> int:  # type: ignore[type-arg]
    return sum(1 for s in steps if s.kind == "explain")


def _example_count(steps: list) -> int:  # type: ignore[type-arg]
    return sum(1 for s in steps if s.kind == "example")


def test_raising_explanation_depth_never_decreases_explain_steps(
    curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(chapter_number=chapter.number)
    counts = []
    for depth in ADMISSIBLE_VALUES[EXPLANATION_DEPTH]:
        steps, _ = plan_lesson(_vector(explanation_depth=depth), selection, curriculum, planner_table)
        counts.append(_explain_count(steps))
    assert counts == sorted(counts)


def test_raising_example_density_never_decreases_example_steps(
    curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(chapter_number=chapter.number)
    counts = []
    for density in ADMISSIBLE_VALUES[EXAMPLE_DENSITY]:
        steps, _ = plan_lesson(_vector(example_density=density), selection, curriculum, planner_table)
        counts.append(_example_count(steps))
    assert counts == sorted(counts)


def test_raising_pacing_never_decreases_section_coverage(
    curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    # A chapter with enough sections that pacing=1..3 can actually differ.
    chapter = next(c for c in curriculum if len(c.sections) >= 3)
    selection = CurriculumSelection(chapter_number=chapter.number)
    coverages = []
    for pacing in ADMISSIBLE_VALUES[PACING]:
        steps, _ = plan_lesson(_vector(pacing=pacing), selection, curriculum, planner_table)
        coverages.append(len({s.section_ref for s in steps if s.kind in ("explain", "example")}))
    assert coverages == sorted(coverages)


def test_pacing_has_no_effect_when_a_specific_section_is_selected(
    curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    chapter = next(c for c in curriculum if len(c.sections) >= 3)
    selection = CurriculumSelection(
        chapter_number=chapter.number, section_number=chapter.sections[0].number
    )
    plans = [
        plan_lesson(_vector(pacing=pacing), selection, curriculum, planner_table)
        for pacing in ADMISSIBLE_VALUES[PACING]
    ]
    first_steps, _ = plans[0]
    for steps, _ in plans[1:]:
        assert steps == first_steps
