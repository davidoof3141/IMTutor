import warnings
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.core.constants import (
    ASSESSMENT_FREQUENCY,
    CONCRETENESS,
    EXAMPLE_DENSITY,
    EXPLANATION_DEPTH,
    PACING,
    REGISTER,
)

Register = Literal["formal", "neutral", "informal"]
AssessmentFrequency = Literal["every_topic", "every_second_topic", "on_request"]

# Our "register" field (formal/neutral/informal register of the tutor's
# language) is unrelated to ABCMeta.register(), which pydantic's metaclass
# also exposes and warns about shadowing. Known-harmless collision.
warnings.filterwarnings(
    "ignore",
    message=r'Field name "register" in ".*" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)


class ControlVector(BaseModel):
    """The six didactic parameters that configure the tutor's prompt."""

    model_config = ConfigDict(frozen=True)

    explanation_depth: int  # 1-5
    example_density: int  # 1-5
    concreteness: int  # 1-5
    register: Register
    pacing: int  # topics per week, 1-3
    assessment_frequency: AssessmentFrequency


# parameter name (a ControlVector field) -> rule id, or constants.DEFAULT_ATTRIBUTION
Attribution = dict[str, str]

# sparse; keys are ControlVector field names, values are admissible values for that field
Override = dict[str, Any]

# Source of truth for each parameter's admissible value domain. Used to enumerate the
# full profile/vector space in tests and to check clause-catalogue totality at startup.
ADMISSIBLE_VALUES: dict[str, list[Any]] = {
    EXPLANATION_DEPTH: [1, 2, 3, 4, 5],
    EXAMPLE_DENSITY: [1, 2, 3, 4, 5],
    CONCRETENESS: [1, 2, 3, 4, 5],
    REGISTER: ["formal", "neutral", "informal"],
    PACING: [1, 2, 3],
    ASSESSMENT_FREQUENCY: ["every_topic", "every_second_topic", "on_request"],
}
