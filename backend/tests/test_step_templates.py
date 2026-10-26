from pathlib import Path

import pytest
import yaml

from app.core.clauses import ClauseCatalogue
from app.core.planner import STEP_KINDS, LessonStep
from app.core.step_templates import StepTemplates, format_step, load_step_templates


def test_shipped_templates_are_total(step_templates: StepTemplates) -> None:
    for kind in STEP_KINDS:
        assert kind in step_templates.templates


def test_incomplete_templates_fail_at_load_time(tmp_path: Path) -> None:
    raw = {
        "version": "broken",
        "templates": {
            "explain": "Explain {section_ref} (pp. {page_start}-{page_end}).",
            "example": "Example for {section_ref}.",
            "checkpoint": "Checkpoint for {section_ref}.",
            # missing "recap"
        },
    }
    path = tmp_path / "step_templates.broken.yaml"
    path.write_text(yaml.safe_dump(raw))

    with pytest.raises(ValueError, match="recap"):
        load_step_templates(path)


def test_format_step_substitutes_only_the_documented_fields(
    step_templates: StepTemplates, catalogue: ClauseCatalogue
) -> None:
    step = LessonStep(
        index=0, kind="explain", section_ref="4.2", page_start=61, page_end=65, concreteness=4
    )
    text = format_step(step, step_templates, catalogue)
    assert "4.2" in text
    assert "61" in text
    assert "65" in text


def test_format_step_uses_the_clause_for_the_steps_own_concreteness(
    step_templates: StepTemplates, catalogue: ClauseCatalogue
) -> None:
    for kind in STEP_KINDS:
        for level in (1, 3, 5):
            step = LessonStep(
                index=0, kind=kind, section_ref="4.2", page_start=61, page_end=65,
                concreteness=level,
            )
            text = " ".join(format_step(step, step_templates, catalogue).split())
            assert catalogue.clauses["concreteness"][level] in text
