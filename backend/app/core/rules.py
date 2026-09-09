"""Rule set: data model, YAML loading, and match evaluation.

The rule set is data, not code (invariant 7): adding a rule is a YAML edit,
never a change to this module. `load_ruleset` performs file I/O and is called
once at process startup; `RuleSet.matches`/`RuleSet.evaluate` take an
already-loaded `RuleSet` and touch no I/O, so they stay safe to call from the
pure `derive()` in mapping.py.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from app.core.profile import Profile


class Rule(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    priority: int
    when: dict[str, list[str]]
    set: dict[str, Any]

    def matches(self, profile: Profile) -> bool:
        for field, admissible in self.when.items():
            if getattr(profile, field) not in admissible:
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
    return RuleSet(version=raw["version"], defaults=raw["defaults"], rules=rules)
