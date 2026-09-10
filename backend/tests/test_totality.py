from app.core.mapping import derive
from app.core.rules import RuleSet
from tests.conftest import (
    GOALS,
    INDUSTRIES,
    LEARNER_TYPES,
    PRIOR_EXPERIENCES,
    ROLES,
    all_profiles,
)


def test_full_profile_space_is_1440() -> None:
    assert (
        len(ROLES) * len(PRIOR_EXPERIENCES) * len(GOALS) * len(INDUSTRIES) * len(LEARNER_TYPES)
        == 1440
    )
    assert len(all_profiles()) == 1440


def test_derive_is_total_over_full_profile_space(ruleset: RuleSet) -> None:
    for profile in all_profiles():
        vector, attribution = derive(profile, ruleset)
        for field in type(vector).model_fields:
            assert getattr(vector, field) is not None
            assert field in attribution
