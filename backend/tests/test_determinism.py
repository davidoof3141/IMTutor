from app.core.mapping import derive
from app.core.rules import RuleSet
from tests.conftest import all_profiles


def test_derive_is_deterministic(ruleset: RuleSet) -> None:
    for profile in all_profiles():
        results = [derive(profile, ruleset) for _ in range(100)]
        first_vector, first_attribution = results[0]
        for vector, attribution in results[1:]:
            assert vector == first_vector
            assert attribution == first_attribution
