import warnings
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.core.constants import (
    ASSESSMENT_FREQUENCY,
    CONCRETENESS,
    EXAMPLE_DENSITY,
    EXAMPLE_DOMAIN,
    EXPLANATION_DEPTH,
    REGISTER,
    REVIEW_SCHEDULE,
)

Register = Literal["polite", "direct"]
# Days between reviews (gap_days). Consumed only by a fixed prompt clause for now.
ReviewSchedule = Literal[2, 7, 14]
AssessmentFrequency = Literal["every_topic", "every_second_topic", "on_request"]
# Which industry the tutor's examples are drawn from. Mirrors profile.Industry
# (the rule set maps one onto the other), but stays a separate type: this is a
# control parameter the learner can override without re-onboarding.
ExampleDomain = Literal[
    "manufacturing",
    "finance",
    "public_sector",
    "healthcare",
    "retail",
    "it_software",
    "logistics",
    "energy",
    "consulting",
    "neutral",
]

# Our "register" field (polite/direct register of the tutor's
# language) is unrelated to ABCMeta.register(), which pydantic's metaclass
# also exposes and warns about shadowing. Known-harmless collision.
warnings.filterwarnings(
    "ignore",
    message=r'Field name "register" in ".*" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)


class ControlVector(BaseModel):
    """The seven didactic parameters that configure the tutor's prompt."""

    model_config = ConfigDict(frozen=True)

    explanation_depth: int  # 1-5
    example_density: int  # 1-5
    concreteness: int  # 1-5
    example_domain: ExampleDomain
    register: Register
    assessment_frequency: AssessmentFrequency
    review_schedule: ReviewSchedule  # gap_days


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
    EXAMPLE_DOMAIN: [
        "manufacturing",
        "finance",
        "public_sector",
        "healthcare",
        "retail",
        "it_software",
        "logistics",
        "energy",
        "consulting",
        "neutral",
    ],
    REGISTER: ["polite", "direct"],
    ASSESSMENT_FREQUENCY: ["every_topic", "every_second_topic", "on_request"],
    REVIEW_SCHEDULE: [2, 7, 14],
}
