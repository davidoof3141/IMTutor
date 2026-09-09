"""Clause catalogue: every admissible value of every parameter maps to exactly
one fixed sentence. A missing entry is a startup error, not a runtime
fallback -- checked by `load_catalogue` at load time.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from app.core.constants import PARAMETER_NAMES
from app.core.vector import ADMISSIBLE_VALUES


class ClauseCatalogue(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    base_instruction: str
    # parameter name -> { admissible value -> fixed clause sentence }
    clauses: dict[str, dict[Any, str]]


def load_catalogue(path: Path) -> ClauseCatalogue:
    raw = yaml.safe_load(path.read_text())
    catalogue = ClauseCatalogue(
        version=raw["version"],
        base_instruction=raw["base_instruction"],
        clauses=raw["clauses"],
    )
    _check_totality(catalogue)
    return catalogue


def _check_totality(catalogue: ClauseCatalogue) -> None:
    missing: list[str] = []
    for field in PARAMETER_NAMES:
        entries = catalogue.clauses.get(field, {})
        for value in ADMISSIBLE_VALUES[field]:
            if value not in entries:
                missing.append(f"{field}={value!r}")
    if missing:
        raise ValueError(
            f"Clause catalogue {catalogue.version} is missing entries for: {', '.join(missing)}"
        )
