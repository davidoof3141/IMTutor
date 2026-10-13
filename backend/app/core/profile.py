from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Self-reported general IT-management experience. At onboarding this is only
# the SEED; a per-chapter diagnostic (core/diagnostic.py) replaces it for that
# chapter's mapping call without ever updating the seed.
PriorKnowledge = Literal["none", "low", "moderate", "high"]
LearningGoal = Literal["certification", "applied", "orientation"]
# How long the learner needs the material to stay available.
RetentionHorizon = Literal["within_2_weeks", "1_to_3_months", "long_term"]
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
# Preferences: NOT mapping inputs. They only select fixed clauses at prompt
# assembly (core/assembler.py) and are invisible to derive().
PresentationStyle = Literal["concise", "balanced", "verbose"]

# The names a rule's `when` block may reference. Deliberately excludes the
# preferences, so a rule can never be conditioned on them.
MAPPING_INPUTS = ("prior_knowledge", "learning_goal", "retention_horizon", "industry")

# Explicit defaults for the mapping inputs (also the onboarding form's initial
# state), so a profile is always complete.
DEFAULT_PRIOR_KNOWLEDGE_SEED: PriorKnowledge = "none"
DEFAULT_LEARNING_GOAL: LearningGoal = "applied"
DEFAULT_RETENTION_HORIZON: RetentionHorizon = "1_to_3_months"
DEFAULT_INDUSTRY: Industry = "neutral"

class Profile(BaseModel):
    """Write-once record of a learner's onboarding answers.

    Changing circumstances means re-onboarding, which creates a new Profile
    (new learner_id) -- never an in-place update of this one.
    """

    model_config = ConfigDict(frozen=True)

    learner_id: str
    user_id: str | None = None
    # --- mapping inputs ---
    prior_knowledge_seed: PriorKnowledge
    learning_goal: LearningGoal
    retention_horizon: RetentionHorizon
    industry: Industry
    # --- preferences (prompt assembly only) ---
    simplified_language: bool
    presentation_style: PresentationStyle
    ruleset_version: str
    created_at: datetime

    @property
    def preferences(self) -> "Preferences":
        return Preferences(
            simplified_language=self.simplified_language,
            presentation_style=self.presentation_style,
        )


class Preferences(BaseModel):
    """Presentation preferences: read only by the prompt assembler."""

    model_config = ConfigDict(frozen=True)

    simplified_language: bool
    presentation_style: PresentationStyle
