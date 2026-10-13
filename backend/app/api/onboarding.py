import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import AppState, Repos, get_current_user, get_repos, get_state
from app.core.constants import CURRENT_RULESET_VERSION
from app.core.mapping import derive
from app.core.profile import (
    DEFAULT_INDUSTRY,
    DEFAULT_LEARNING_GOAL,
    DEFAULT_PRIOR_KNOWLEDGE_SEED,
    DEFAULT_RETENTION_HORIZON,
    Industry,
    LearningGoal,
    PresentationStyle,
    PriorKnowledge,
    Profile,
    RetentionHorizon,
)
from app.core.vector import Attribution, ControlVector
from app.store.study_mode import StudyModeState
from app.store.users import User

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingRequest(BaseModel):
    """Four mapping inputs (each with an explicit default) plus two preferences."""

    prior_knowledge_seed: PriorKnowledge = DEFAULT_PRIOR_KNOWLEDGE_SEED
    learning_goal: LearningGoal = DEFAULT_LEARNING_GOAL
    retention_horizon: RetentionHorizon = DEFAULT_RETENTION_HORIZON
    industry: Industry = DEFAULT_INDUSTRY
    simplified_language: bool = False
    presentation_style: PresentationStyle = "balanced"


class OnboardingResponse(BaseModel):
    profile: Profile
    derived: ControlVector
    attribution: Attribution


@router.post("", response_model=OnboardingResponse)
def onboard(
    body: OnboardingRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> OnboardingResponse:
    now = datetime.now(UTC)
    profile = Profile(
        learner_id=str(uuid.uuid4()),
        user_id=user.id,
        prior_knowledge_seed=body.prior_knowledge_seed,
        learning_goal=body.learning_goal,
        retention_horizon=body.retention_horizon,
        industry=body.industry,
        simplified_language=body.simplified_language,
        presentation_style=body.presentation_style,
        ruleset_version=CURRENT_RULESET_VERSION,
        created_at=now,
    )
    repos.profiles.create(profile)

    # Link-invited accounts (the A/B comparison study's participants) land
    # straight on the Lernplan -- their curriculum is already narrowed to
    # chapters 3.1-3.3 (see app/api/study_mode.py), so free exploration adds
    # nothing and the schedule is the more useful default view.
    if user.has_login_link:
        repos.study_mode.set(profile.learner_id, StudyModeState(mode="training"))

    ruleset = state.rulesets[profile.ruleset_version]
    derived, attribution = derive(profile, ruleset)

    return OnboardingResponse(profile=profile, derived=derived, attribution=attribution)
