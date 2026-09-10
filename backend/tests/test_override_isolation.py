from app.core.mapping import derive, effective
from app.core.rules import RuleSet
from app.store.db import Conn
from app.store.overrides import OverrideRepository
from tests.conftest import make_profile


def test_effective_with_empty_override_equals_derived(ruleset: RuleSet) -> None:
    profile = make_profile()
    derived, _ = derive(profile, ruleset)
    assert effective(derived, {}) == derived


def test_override_then_full_revert_recovers_derived(ruleset: RuleSet) -> None:
    profile = make_profile()
    derived, _ = derive(profile, ruleset)

    overridden = effective(derived, {"concreteness": 1, "register": "formal"})
    assert overridden != derived

    reverted = effective(derived, {})
    assert reverted == derived, "the derived vector must remain recoverable"


def test_repository_override_sequence_leaves_derived_unaffected(
    db_conn: Conn, ruleset: RuleSet
) -> None:
    repo = OverrideRepository(db_conn)
    learner_id = "learner-1"
    profile = make_profile(learner_id=learner_id)

    derived_before, _ = derive(profile, ruleset)

    repo.set(learner_id, {"concreteness": 5})
    repo.set(learner_id, {"register": "formal"})
    repo.delete_field(learner_id, "concreteness")
    repo.delete_all(learner_id)

    derived_after, _ = derive(profile, ruleset)
    assert derived_after == derived_before

    assert repo.get(learner_id) == {}
    assert effective(derived_after, repo.get(learner_id)) == derived_after
