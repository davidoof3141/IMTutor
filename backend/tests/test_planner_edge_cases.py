"""Edge cases exercised with synthetic curriculum data rather than the real
book -- the real curriculum happens not to have a section-less chapter, and
its section counts don't cover every checkpoint-parity case, so these are
pinned explicitly instead of hoping the book contains them.
"""

from pathlib import Path

import pytest

from app.core.planner import CurriculumSelection, PlannerTable, load_planner_table, plan_lesson
from app.core.vector import ControlVector
from app.rag.toc import Chapter, Section

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"

CHAPTER_NO_SECTIONS = Chapter(number="9", title="Short", page_start=500, page_end=505, sections=[])

CHAPTER_THREE_SECTIONS = Chapter(
    number="7",
    title="Three",
    page_start=100,
    page_end=130,
    sections=[
        Section(number="7.1", title="A", page_start=100, page_end=109),
        Section(number="7.2", title="B", page_start=110, page_end=119),
        Section(number="7.3", title="C", page_start=120, page_end=130),
    ],
)


def _vector(**overrides: object) -> ControlVector:
    base: dict[str, object] = {
        "explanation_depth": 3,
        "example_density": 3,
        "concreteness": 3,
        "register": "neutral",
        "pacing": 3,
        "assessment_frequency": "every_topic",
    }
    base.update(overrides)
    return ControlVector.model_validate(base)


def test_chapter_with_no_sections_becomes_one_whole_chapter_unit(
    planner_table: PlannerTable,
) -> None:
    curriculum = [CHAPTER_NO_SECTIONS]
    selection = CurriculumSelection(chapter_number="9")

    steps, _ = plan_lesson(_vector(), selection, curriculum, planner_table)

    units = {s.section_ref for s in steps if s.kind in ("explain", "example", "checkpoint")}
    assert units == {"9"}
    assert all(s.page_start == 500 and s.page_end == 505 for s in steps if s.kind != "recap")
    assert steps[-1].kind == "recap"
    assert steps[-1].section_ref == "9"


def test_pacing_beyond_chapter_length_is_capped_not_invented(planner_table: PlannerTable) -> None:
    curriculum = [CHAPTER_THREE_SECTIONS]
    selection = CurriculumSelection(chapter_number="7")

    steps, _ = plan_lesson(_vector(pacing=3), selection, curriculum, planner_table)

    covered = {s.section_ref for s in steps if s.kind in ("explain", "example", "checkpoint")}
    assert covered <= {"7.1", "7.2", "7.3"}
    assert len(covered) <= 3


def test_every_second_topic_checkpoint_after_pairs_plus_trailing_odd(
    planner_table: PlannerTable,
) -> None:
    curriculum = [CHAPTER_THREE_SECTIONS]
    selection = CurriculumSelection(chapter_number="7")

    steps, _ = plan_lesson(
        _vector(pacing=3, assessment_frequency="every_second_topic"),
        selection,
        curriculum,
        planner_table,
    )

    checkpoints = [s for s in steps if s.kind == "checkpoint"]
    # 3 sections, every-second pattern -> one checkpoint after 7.1+7.2, one
    # trailing checkpoint for the unpaired 7.3.
    assert len(checkpoints) == 2
    assert checkpoints[0].section_ref == "7.2"
    assert checkpoints[0].page_start == 100  # spans from the first of the pair
    assert checkpoints[0].page_end == 119
    assert checkpoints[1].section_ref == "7.3"


def test_recap_section_ref_is_the_chapter_for_a_multi_section_lesson(
    planner_table: PlannerTable,
) -> None:
    curriculum = [CHAPTER_THREE_SECTIONS]
    selection = CurriculumSelection(chapter_number="7")

    steps, rationale = plan_lesson(_vector(pacing=3), selection, curriculum, planner_table)

    recap = steps[-1]
    assert recap.section_ref == "7"
    assert recap.page_start == 100
    assert recap.page_end == 130
    assert rationale[recap.index] == "always"


def test_recap_section_ref_is_the_section_for_a_single_section_lesson(
    planner_table: PlannerTable,
) -> None:
    curriculum = [CHAPTER_THREE_SECTIONS]
    selection = CurriculumSelection(chapter_number="7", section_number="7.2")

    steps, _ = plan_lesson(_vector(), selection, curriculum, planner_table)

    recap = steps[-1]
    assert recap.section_ref == "7.2"
    assert recap.page_start == 110
    assert recap.page_end == 119


def test_unknown_chapter_raises() -> None:
    table = load_planner_table(RULES_DIR / "planner.v1.yaml")
    with pytest.raises(ValueError, match="unknown chapter"):
        plan_lesson(_vector(), CurriculumSelection(chapter_number="404"), [], table)


def test_unknown_section_raises(planner_table: PlannerTable) -> None:
    curriculum = [CHAPTER_THREE_SECTIONS]
    with pytest.raises(ValueError, match="unknown section"):
        plan_lesson(
            _vector(),
            CurriculumSelection(chapter_number="7", section_number="7.9"),
            curriculum,
            planner_table,
        )
