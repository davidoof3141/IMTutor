from app.core.mapping import derive
from app.core.rules import RuleSet
from tests.conftest import (
    GOALS,
    LEARNER_TYPES,
    PRIOR_EXPERIENCES,
    ROLES,
    STUDY_TIMES,
    all_profiles,
)


def test_full_profile_space_is_432() -> None:
    assert (
        len(ROLES) * len(PRIOR_EXPERIENCES) * len(GOALS) * len(STUDY_TIMES) * len(LEARNER_TYPES)
        == 432
    )
    assert len(all_profiles()) == 432


def test_derive_is_total_over_full_profile_space(ruleset: RuleSet) -> None:
    for profile in all_profiles():
        vector, attribution = derive(profile, ruleset)
        for field in type(vector).model_fields:
            assert getattr(vector, field) is not None
            assert field in attribution
