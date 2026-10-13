import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

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
    band_from_exam_date,
)
from app.core.vector import Attribution, ControlVector
from app.store.study_mode import StudyModeState
from app.store.users import User

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingRequest(BaseModel):
    """Four mapping inputs (each with an explicit default) plus two preferences.

    The retention horizon is given either as a band or as an exam date; a date
    is converted to a band here, once, and only the band is stored.
    """

    prior_knowledge_seed: PriorKnowledge = DEFAULT_PRIOR_KNOWLEDGE_SEED
    learning_goal: LearningGoal = DEFAULT_LEARNING_GOAL
    retention_horizon: RetentionHorizon | None = None
    exam_date: date | None = None
    industry: Industry = DEFAULT_INDUSTRY
    simplified_language: bool = False
    presentation_style: PresentationStyle = "balanced"

    @model_validator(mode="after")
    def _one_horizon_source(self) -> "OnboardingRequest":
        if self.retention_horizon is not None and self.exam_date is not None:
            raise ValueError("give either retention_horizon or exam_date, not both")
        return self


class OnboardingResponse(BaseModel):
    profile: Profile
    derived: ControlVector
    attribution: Attribution


def _resolve_horizon(body: OnboardingRequest, now: datetime) -> RetentionHorizon:
    if body.exam_date is not None:
        try:
            return band_from_exam_date(body.exam_date, now.date())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return body.retention_horizon or DEFAULT_RETENTION_HORIZON


@router.post("", response_model=OnboardingResponse)
def onboard(
    body: OnboardingRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> OnboardingResponse:
    now = datetime.now(UTC)  # the only clock read; derive() never sees it
    profile = Profile(
        learner_id=str(uuid.uuid4()),
        user_id=user.id,
        prior_knowledge_seed=body.prior_knowledge_seed,
        learning_goal=body.learning_goal,
        retention_horizon=_resolve_horizon(body, now),
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
