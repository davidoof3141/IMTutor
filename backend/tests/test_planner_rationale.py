from app.core.mapping import derive
from app.core.planner import Curriculum, CurriculumSelection, PlannerTable, plan_lesson
from app.core.rules import RuleSet
from tests.conftest import make_profile


def test_every_step_has_a_rationale_entry(
    ruleset: RuleSet, curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    profile = make_profile(goal="certification")
    vector, _ = derive(profile, ruleset)
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(chapter_number=chapter.number)

    steps, rationale = plan_lesson(vector, selection, curriculum, planner_table)
    assert set(rationale) == {s.index for s in steps}


def test_rationale_attributes_each_kind_to_its_parameter(
    ruleset: RuleSet, curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    profile = make_profile(goal="certification")  # every_topic -> guarantees checkpoints
    vector, _ = derive(profile, ruleset)
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(chapter_number=chapter.number)

    steps, rationale = plan_lesson(vector, selection, curriculum, planner_table)
    kinds_seen = {s.kind for s in steps}
    assert kinds_seen >= {"explain", "checkpoint", "recap"}

    for step in steps:
        cause = rationale[step.index]
        if step.kind == "explain":
            assert cause == f"explanation_depth={vector.explanation_depth}"
        elif step.kind == "example":
            assert cause == f"example_density={vector.example_density}"
        elif step.kind == "checkpoint":
            assert cause == f"assessment_frequency={vector.assessment_frequency}"
        elif step.kind == "recap":
            assert cause == "always"


def test_on_request_assessment_frequency_produces_no_checkpoints(
    ruleset: RuleSet, curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    profile = make_profile(goal="orientation")  # -> assessment_frequency = on_request
    vector, _ = derive(profile, ruleset)
    assert vector.assessment_frequency == "on_request"
    chapter = next(c for c in curriculum if c.sections)
    selection = CurriculumSelection(chapter_number=chapter.number)

    steps, _ = plan_lesson(vector, selection, curriculum, planner_table)
    assert not any(s.kind == "checkpoint" for s in steps)
