from app.core.mapping import derive
from app.core.rules import RuleSet
from tests.conftest import (
    GOALS,
    INDUSTRIES,
    PRIOR_KNOWLEDGES,
    RETENTION_HORIZONS,
    all_profiles,
)


def test_full_mapping_input_space_is_360() -> None:
    assert len(PRIOR_KNOWLEDGES) * len(GOALS) * len(RETENTION_HORIZONS) * len(INDUSTRIES) == 360
    assert len(all_profiles()) == 360


def test_derive_is_total_over_full_profile_space(ruleset: RuleSet) -> None:
    for profile in all_profiles():
        vector, attribution = derive(profile, ruleset)
        for field in type(vector).model_fields:
            assert getattr(vector, field) is not None
            assert field in attribution


def test_derive_is_total_with_a_chapter_level_over_the_whole_space(ruleset: RuleSet) -> None:
    for profile in all_profiles():
        for level in PRIOR_KNOWLEDGES:
            vector, attribution = derive(profile, ruleset, level)
            for field in type(vector).model_fields:
                assert getattr(vector, field) is not None
                assert field in attribution
