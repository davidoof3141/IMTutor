from pathlib import Path

import pytest
import yaml

from app.core.clauses import ClauseCatalogue, load_catalogue
from app.core.constants import PARAMETER_NAMES
from app.core.vector import ADMISSIBLE_VALUES


def test_shipped_catalogue_is_total(catalogue: ClauseCatalogue) -> None:
    for field in PARAMETER_NAMES:
        for value in ADMISSIBLE_VALUES[field]:
            assert value in catalogue.clauses[field]


def test_incomplete_catalogue_fails_at_load_time(tmp_path: Path) -> None:
    raw = {
        "version": "broken",
        "base_instruction": "x",
        "clauses": {
            "explanation_depth": {1: "a", 2: "b", 3: "c", 4: "d"},  # missing 5
            "example_density": {v: "x" for v in ADMISSIBLE_VALUES["example_density"]},
            "concreteness": {v: "x" for v in ADMISSIBLE_VALUES["concreteness"]},
            "example_domain": {v: "x" for v in ADMISSIBLE_VALUES["example_domain"]},
            "register": {v: "x" for v in ADMISSIBLE_VALUES["register"]},
            "assessment_frequency": {v: "x" for v in ADMISSIBLE_VALUES["assessment_frequency"]},
        },
    }
    path = tmp_path / "clauses.broken.yaml"
    path.write_text(yaml.safe_dump(raw))

    with pytest.raises(ValueError, match="explanation_depth"):
        load_catalogue(path)
