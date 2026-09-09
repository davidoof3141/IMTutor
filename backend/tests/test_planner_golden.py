"""Snapshot the full lesson plan + rationale for a fixed set of
(profile, selection) pairs.

If one of these fails after a deliberate planner-table change, regenerate
the golden file's content with the same inputs via plan_lesson() and review
the diff before committing it -- that review is the point of this test, same
as test_golden_prompts.py for the assembled system prompt.
"""

import json
from pathlib import Path

import pytest

from app.core.mapping import derive
from app.core.planner import Curriculum, CurriculumSelection, PlannerTable, plan_lesson
from app.core.rules import RuleSet
from tests.conftest import make_profile

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "planner"


def _select_single_section(curriculum: Curriculum) -> CurriculumSelection:
    chapter = next(c for c in curriculum if c.sections)
    return CurriculumSelection(
        chapter_number=chapter.number, section_number=chapter.sections[0].number
    )


# (profile, selection-builder) pairs. The selection-builder takes the
# extracted curriculum and returns a CurriculumSelection, so cases stay
# robust to exact chapter/section numbering rather than hardcoding one.
CASES = {
    "novice_practitioner_whole_chapter": (
        make_profile(
            role="practitioner",
            prior_experience="none",
            goal="certification",
            study_time="under_2h",
        ),
        lambda curriculum: CurriculumSelection(
            chapter_number=next(c for c in curriculum if len(c.sections) >= 3).number
        ),
    ),
    "expert_academic_single_section": (
        make_profile(
            role="academic", prior_experience="high", goal="orientation", study_time="over_4h"
        ),
        _select_single_section,
    ),
    "moderate_practitioner_applied_long_chapter": (
        make_profile(
            role="practitioner",
            prior_experience="moderate",
            goal="applied_competence",
            study_time="2_to_4h",
        ),
        lambda curriculum: CurriculumSelection(
            chapter_number=max(curriculum, key=lambda c: len(c.sections)).number
        ),
    ),
}


def _serialize(steps: list, rationale: dict) -> str:  # type: ignore[type-arg]
    payload = {
        "steps": [s.model_dump() for s in steps],
        "rationale": {str(k): v for k, v in rationale.items()},
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize("case_name", sorted(CASES))
def test_golden_plan(
    case_name: str, ruleset: RuleSet, curriculum: Curriculum, planner_table: PlannerTable
) -> None:
    profile, build_selection = CASES[case_name]
    selection = build_selection(curriculum)
    vector, _ = derive(profile, ruleset)
    steps, rationale = plan_lesson(vector, selection, curriculum, planner_table)

    actual = _serialize(steps, rationale)
    expected = (GOLDEN_DIR / f"{case_name}.json").read_text()
    assert actual == expected
