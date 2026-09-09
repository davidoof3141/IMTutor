from app.core.mapping import derive
from app.core.planner import Curriculum, CurriculumSelection, PlannerTable, plan_lesson
from app.core.rules import RuleSet
from tests.conftest import make_profile


def test_plan_lesson_is_deterministic(
    ruleset: RuleSet, curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    profile = make_profile(role="practitioner", prior_experience="none")
    vector, _ = derive(profile, ruleset)
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(chapter_number=chapter.number)

    results = [plan_lesson(vector, selection, curriculum, planner_table) for _ in range(100)]
    first_steps, first_rationale = results[0]
    for steps, rationale in results[1:]:
        assert steps == first_steps
        assert rationale == first_rationale


def test_plan_lesson_is_deterministic_for_a_single_section(
    ruleset: RuleSet, curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    profile = make_profile(role="academic", prior_experience="high")
    vector, _ = derive(profile, ruleset)
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(
        chapter_number=chapter.number, section_number=chapter.sections[0].number
    )

    results = [plan_lesson(vector, selection, curriculum, planner_table) for _ in range(100)]
    first_steps, first_rationale = results[0]
    for steps, rationale in results[1:]:
        assert steps == first_steps
        assert rationale == first_rationale
