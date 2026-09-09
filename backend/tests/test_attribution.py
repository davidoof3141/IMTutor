from app.core.constants import DEFAULT_ATTRIBUTION, PARAMETER_NAMES
from app.core.mapping import derive
from app.core.rules import RuleSet
from tests.conftest import all_profiles


def test_every_parameter_is_attributed(ruleset: RuleSet) -> None:
    rule_ids = {rule.id for rule in ruleset.rules}
    for profile in all_profiles():
        _, attribution = derive(profile, ruleset)
        assert set(attribution.keys()) == set(PARAMETER_NAMES)
        for value in attribution.values():
            assert value == DEFAULT_ATTRIBUTION or value in rule_ids


def test_at_least_one_profile_hits_every_rule(ruleset: RuleSet) -> None:
    """Sanity check that the ruleset fixture actually exercises every rule."""
    seen_rule_ids: set[str] = set()
    for profile in all_profiles():
        _, attribution = derive(profile, ruleset)
        seen_rule_ids.update(v for v in attribution.values() if v != "default")
    assert seen_rule_ids == {rule.id for rule in ruleset.rules}
