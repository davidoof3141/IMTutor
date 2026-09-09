"""Snapshot the assembled system prompt for a fixed set of profiles.

If one of these fails after a deliberate wording change, regenerate the
golden file's content with the same profile via assemble() and review the
diff before committing it -- that review is the point of this test.
"""

from pathlib import Path

import pytest

from app.core.assembler import assemble
from app.core.clauses import ClauseCatalogue
from app.core.mapping import derive, effective
from app.core.rules import RuleSet
from tests.conftest import make_profile

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

CASES = {
    "novice_practitioner_certification": make_profile(
        role="practitioner",
        prior_experience="none",
        goal="certification",
        study_time="under_2h",
        learner_type="visuell",
    ),
    "expert_academic_orientation": make_profile(
        role="academic",
        prior_experience="high",
        goal="orientation",
        study_time="over_4h",
        learner_type="auditiv",
    ),
    "moderate_practitioner_applied": make_profile(
        role="practitioner",
        prior_experience="moderate",
        goal="applied_competence",
        study_time="2_to_4h",
        learner_type="motorisch",
    ),
}


@pytest.mark.parametrize("case_name", sorted(CASES))
def test_golden_prompt(case_name: str, ruleset: RuleSet, catalogue: ClauseCatalogue) -> None:
    profile = CASES[case_name]
    derived, _ = derive(profile, ruleset)
    prompt = assemble(effective(derived, {}), catalogue)

    expected = (GOLDEN_DIR / f"{case_name}.txt").read_text()
    assert prompt == expected
