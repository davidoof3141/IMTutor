"""Rule set: data model, YAML loading, and match evaluation.

The rule set is data, not code (invariant 7): adding a rule is a YAML edit,
never a change to this module. `load_ruleset` performs file I/O and is called
once at process startup; `RuleSet.matches`/`RuleSet.evaluate` take an
already-loaded `RuleSet` and touch no I/O, so they stay safe to call from the
pure `derive()` in mapping.py.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from app.core.profile import MAPPING_INPUTS


class Rule(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    priority: int
    when: dict[str, list[str]]
    set: dict[str, Any]

    def matches(self, inputs: Mapping[str, str]) -> bool:
        """`inputs` is the mapping-input dict built by `mapping.mapping_inputs`."""
        for field, admissible in self.when.items():
            if inputs[field] not in admissible:
                return False
        return True


class RuleSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    defaults: dict[str, Any]
    rules: tuple[Rule, ...]

    def rules_by_priority(self) -> tuple[Rule, ...]:
        """Highest priority first; ties broken by declaration order (stable sort)."""
        return tuple(sorted(self.rules, key=lambda r: r.priority, reverse=True))


def _normalize_when(when: dict[str, Any]) -> dict[str, list[str]]:
    """YAML allows `field: value` as shorthand for `field: [value]`."""
    return {field: value if isinstance(value, list) else [value] for field, value in when.items()}


def load_ruleset(path: Path) -> RuleSet:
    raw = yaml.safe_load(path.read_text())
    rules = tuple(
        Rule(id=r["id"], priority=r["priority"], when=_normalize_when(r["when"]), set=r["set"])
        for r in raw["rules"]
    )
    for rule in rules:
        unknown = sorted(set(rule.when) - set(MAPPING_INPUTS))
        if unknown:
            raise ValueError(
                f"Rule {rule.id!r} conditions on {unknown}, which are not mapping inputs "
                f"({', '.join(MAPPING_INPUTS)})"
            )
    return RuleSet(version=raw["version"], defaults=raw["defaults"], rules=rules)
