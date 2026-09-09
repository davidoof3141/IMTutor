"""The pure control-layer mapping (invariants 1-6).

No network, no clock, no randomness, no file I/O, no global state, and no LLM
import -- directly or transitively. Enforced by tests/test_purity.py.
"""

from app.core.constants import DEFAULT_ATTRIBUTION
from app.core.profile import Profile
from app.core.rules import RuleSet
from app.core.vector import Attribution, ControlVector, Override


def derive(profile: Profile, ruleset: RuleSet) -> tuple[ControlVector, Attribution]:
    """Total, deterministic: every admissible profile maps to a full vector.

    Rules are applied lowest-priority-first, so a higher-priority rule that
    writes the same parameter is applied later and wins; the attribution is
    updated alongside so it always reflects the last (highest-priority)
    writer. Ties in priority are broken by declaration order (later wins).
    """
    values: dict[str, object] = dict(ruleset.defaults)
    attribution: Attribution = {field: DEFAULT_ATTRIBUTION for field in ruleset.defaults}

    ascending_rules = tuple(reversed(ruleset.rules_by_priority()))
    for rule in ascending_rules:
        if not rule.matches(profile):
            continue
        for field, value in rule.set.items():
            values[field] = value
            attribution[field] = rule.id

    return ControlVector.model_validate(values), attribution


def effective(derived: ControlVector, override: Override) -> ControlVector:
    """Apply a sparse override over the derived vector without mutating it."""
    return derived.model_copy(update=dict(override))
