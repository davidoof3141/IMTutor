from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["practitioner", "analyst", "academic"]
PriorExperience = Literal["none", "low", "moderate", "high"]
Goal = Literal["certification", "applied_competence", "orientation"]
# The learner's working context; decides which world the tutor's examples
# are drawn from (maps to the example_domain control parameter).
Industry = Literal[
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
# Lerntyp (Vester): how the learner prefers to take in new material.
LearnerType = Literal["visuell", "auditiv", "kommunikativ", "motorisch"]


class Profile(BaseModel):
    """Write-once record of a learner's onboarding answers.

    Changing circumstances means re-onboarding, which creates a new Profile
    (new learner_id) -- never an in-place update of this one.
    """

    model_config = ConfigDict(frozen=True)

    learner_id: str
    user_id: str | None = None
    role: Role
    prior_experience: PriorExperience
    goal: Goal
    industry: Industry
    learner_type: LearnerType
    ruleset_version: str
    created_at: datetime
