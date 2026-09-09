import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import AppState, Repos, get_current_user, get_repos, get_state
from app.core.constants import CURRENT_RULESET_VERSION
from app.core.mapping import derive
from app.core.profile import Goal, LearnerType, PriorExperience, Profile, Role, StudyTime
from app.core.vector import Attribution, ControlVector
from app.store.users import User

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingRequest(BaseModel):
    role: Role
    prior_experience: PriorExperience
    goal: Goal
    study_time: StudyTime
    learner_type: LearnerType


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
    profile = Profile(
        learner_id=str(uuid.uuid4()),
        user_id=user.id,
        role=body.role,
        prior_experience=body.prior_experience,
        goal=body.goal,
        study_time=body.study_time,
        learner_type=body.learner_type,
        ruleset_version=CURRENT_RULESET_VERSION,
        created_at=datetime.now(UTC),
    )
    repos.profiles.create(profile)

    ruleset = state.rulesets[profile.ruleset_version]
    derived, attribution = derive(profile, ruleset)

    return OnboardingResponse(profile=profile, derived=derived, attribution=attribution)
