"""Prompt assembly: selection and concatenation only.

Must never generate, paraphrase, or template-interpolate free text -- every
sentence in the output already exists verbatim in the clause catalogue.
"""

from app.core.clauses import ClauseCatalogue
from app.core.constants import PARAMETER_NAMES
from app.core.profile import Preferences
from app.core.vector import ControlVector


def assemble(
    vector: ControlVector,
    catalogue: ClauseCatalogue,
    preferences: Preferences | None = None,
) -> str:
    """One clause per control parameter, then (optionally) one per preference.

    Preferences are not part of the vector or the mapping; they only add fixed
    sentences here. Omit them (the generic comparison baseline) for none.
    """
    lines = [catalogue.base_instruction]
    for field in PARAMETER_NAMES:
        value = getattr(vector, field)
        lines.append(catalogue.clauses[field][value])
    if preferences is not None:
        if preferences.simplified_language:
            lines.append(catalogue.preferences["simplified_language"][True])
        lines.append(catalogue.preferences["presentation_style"][preferences.presentation_style])
        if preferences.learner_type != "none":
            lines.append(catalogue.preferences["learner_type"][preferences.learner_type])
    return "\n".join(lines)
