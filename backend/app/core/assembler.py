"""Prompt assembly: selection and concatenation only.

Must never generate, paraphrase, or template-interpolate free text -- every
sentence in the output already exists verbatim in the clause catalogue.
"""

from app.core.clauses import ClauseCatalogue
from app.core.constants import PARAMETER_NAMES
from app.core.vector import ControlVector


def assemble(vector: ControlVector, catalogue: ClauseCatalogue) -> str:
    lines = [catalogue.base_instruction]
    for field in PARAMETER_NAMES:
        value = getattr(vector, field)
        lines.append(catalogue.clauses[field][value])
    return "\n".join(lines)
