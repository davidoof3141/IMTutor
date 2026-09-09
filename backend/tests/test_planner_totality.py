from app.core.mapping import derive
from app.core.planner import Curriculum, CurriculumSelection, PlannerTable, plan_lesson
from app.core.rules import RuleSet
from app.rag.toc import Chapter
from tests.conftest import all_profiles


def _all_selections(curriculum: Curriculum) -> list[CurriculumSelection]:
    selections = []
    for chapter in curriculum:
        selections.append(CurriculumSelection(chapter_number=chapter.number))
        selections.extend(
            CurriculumSelection(chapter_number=chapter.number, section_number=section.number)
            for section in chapter.sections
        )
    return selections


def test_curriculum_has_chapters_and_sections(curriculum: list[Chapter]) -> None:
    assert len(curriculum) > 0
    assert sum(len(c.sections) for c in curriculum) > 0


def test_plan_lesson_is_total_over_profiles_and_curriculum(
    ruleset: RuleSet, curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    selections = _all_selections(curriculum)
    for profile in all_profiles():
        vector, _ = derive(profile, ruleset)
        for selection in selections:
            steps, rationale = plan_lesson(vector, selection, curriculum, planner_table)
            assert steps, f"empty plan for {profile} / {selection}"
            assert [s.index for s in steps] == list(range(len(steps))), "gap in step index"
            assert steps[-1].kind == "recap"
            assert sum(1 for s in steps if s.kind == "recap") == 1
            assert set(rationale) == set(range(len(steps)))
