"""Concreteness fading is a pure function of the plan position (invariant 6):
the k-th explain/example step of a section is given at start - k, never below
the floor; checkpoints and the recap sit at the floor; the fade restarts in
every section.
"""

from app.core.planner import (
    Curriculum,
    CurriculumSelection,
    PlannerTable,
    faded_concreteness,
    plan_lesson,
)
from app.core.vector import ControlVector


def _vector(**overrides: object) -> ControlVector:
    base: dict[str, object] = {
        "explanation_depth": 4,
        "example_density": 4,
        "concreteness": 5,
        "example_domain": "neutral",
        "register": "polite",
        "review_schedule": 7,
        "assessment_frequency": "every_topic",
    }
    base.update(overrides)
    return ControlVector.model_validate(base)


def test_faded_concreteness_values(planner_table: PlannerTable) -> None:
    # floor 2, step 1
    assert [faded_concreteness(5, k, planner_table) for k in range(6)] == [5, 4, 3, 2, 2, 2]
    assert [faded_concreteness(3, k, planner_table) for k in range(4)] == [3, 2, 2, 2]
    # a start level at or below the floor is kept, never raised
    assert [faded_concreteness(2, k, planner_table) for k in range(3)] == [2, 2, 2]
    assert [faded_concreteness(1, k, planner_table) for k in range(3)] == [1, 1, 1]


def test_each_section_fades_from_the_start_level(
    curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    chapter = next(c for c in curriculum if len(c.sections) >= 2)
    steps, _ = plan_lesson(
        _vector(), CurriculumSelection(chapter_number=chapter.number), curriculum, planner_table
    )
    for section in chapter.sections:
        content = [s for s in steps if s.section_ref == section.number and s.kind in ("explain", "example")]
        levels = [s.concreteness for s in content]
        assert levels[0] == 5, "fade restarts at the start level in every section"
        assert levels == sorted(levels, reverse=True), "never rises within a section"
        assert min(levels) >= planner_table.concreteness_floor


def test_checkpoints_and_recap_use_the_floor(
    curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    chapter = next(c for c in curriculum if c.sections)
    steps, _ = plan_lesson(
        _vector(), CurriculumSelection(chapter_number=chapter.number), curriculum, planner_table
    )
    closing = [s for s in steps if s.kind in ("checkpoint", "recap")]
    assert closing
    assert {s.concreteness for s in closing} == {planner_table.concreteness_floor}


def test_fading_ignores_nothing_but_position(
    curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    """Same inputs, same levels; and a different start level shifts the whole
    fade without changing the number or kinds of steps."""
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(chapter_number=chapter.number)
    a, _ = plan_lesson(_vector(concreteness=5), selection, curriculum, planner_table)
    b, _ = plan_lesson(_vector(concreteness=5), selection, curriculum, planner_table)
    c, _ = plan_lesson(_vector(concreteness=3), selection, curriculum, planner_table)
    assert a == b
    assert [s.kind for s in a] == [s.kind for s in c]
    assert [s.concreteness for s in a] != [s.concreteness for s in c]
