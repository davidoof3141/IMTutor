from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["practitioner", "analyst", "academic"]
PriorExperience = Literal["none", "low", "moderate", "high"]
Goal = Literal["certification", "applied_competence", "orientation"]
StudyTime = Literal["under_2h", "2_to_4h", "over_4h"]
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
    study_time: StudyTime
    learner_type: LearnerType
    ruleset_version: str
    created_at: datetime
