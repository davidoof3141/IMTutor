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
    "novice_certification_short": make_profile(
        prior_knowledge_seed="none",
        learning_goal="certification",
        retention_horizon="within_2_weeks",
        industry="healthcare",
    ),
    "expert_orientation": make_profile(
        prior_knowledge_seed="high",
        learning_goal="orientation",
        retention_horizon="long_term",
        industry="finance",
    ),
    "moderate_applied": make_profile(
        prior_knowledge_seed="moderate",
        learning_goal="applied",
        retention_horizon="long_term",
        industry="manufacturing",
        simplified_language=True,
        presentation_style="concise",
    ),
}


@pytest.mark.parametrize("case_name", sorted(CASES))
def test_golden_prompt(case_name: str, ruleset: RuleSet, catalogue: ClauseCatalogue) -> None:
    profile = CASES[case_name]
    derived, _ = derive(profile, ruleset)
    prompt = assemble(effective(derived, {}), catalogue, profile.preferences)

    expected = (GOLDEN_DIR / f"{case_name}.txt").read_text()
    assert prompt == expected
