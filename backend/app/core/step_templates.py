"""Lesson step templates: every StepKind maps to exactly one fixed
instruction sentence. A missing entry is a startup error, not a runtime
fallback -- same rule as clauses.py's catalogue totality check.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from app.core.planner import STEP_KINDS, LessonStep, StepKind


class StepTemplates(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    templates: dict[StepKind, str]


def load_step_templates(path: Path) -> StepTemplates:
    raw = yaml.safe_load(path.read_text())
    templates = StepTemplates(version=raw["version"], templates=raw["templates"])
    _check_totality(templates)
    return templates


def _check_totality(templates: StepTemplates) -> None:
    missing = [kind for kind in STEP_KINDS if kind not in templates.templates]
    if missing:
        raise ValueError(
            f"Step template set {templates.version} is missing entries for: {missing}"
        )


def format_step(step: LessonStep, templates: StepTemplates) -> str:
    """Fixed template plus substitution of `section_ref`/`page_start`/
    `page_end` only -- no other interpolation, no free text. Same spirit as
    `app.rag.toc.format_focus`."""
    return templates.templates[step.kind].format(
        section_ref=step.section_ref,
        page_start=step.page_start,
        page_end=step.page_end,
    )
