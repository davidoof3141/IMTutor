from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import (
    AppState,
    Repos,
    authorize_learner,
    get_current_user,
    get_repos,
    get_state,
)
from app.core.constants import PARAMETER_NAMES
from app.core.mapping import derive, effective
from app.core.profile import Profile
from app.core.vector import (
    AssessmentFrequency,
    Attribution,
    ControlVector,
    ExampleDomain,
    Override,
    Register,
)
from app.store.users import User

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    profile: Profile
    derived: ControlVector
    override: Override
    effective: ControlVector
    attribution: Attribution


class OverrideRequest(BaseModel):
    explanation_depth: int | None = None
    example_density: int | None = None
    concreteness: int | None = None
    example_domain: ExampleDomain | None = None
    register: Register | None = None
    assessment_frequency: AssessmentFrequency | None = None

    def as_sparse_dict(self) -> Override:
        return {k: v for k, v in self.model_dump().items() if v is not None}


def _load_config(learner_id: str, state: AppState, repos: Repos) -> ConfigResponse:
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")

    ruleset = state.rulesets[profile.ruleset_version]
    derived, attribution = derive(profile, ruleset)
    override = repos.overrides.get(learner_id)
    return ConfigResponse(
        profile=profile,
        derived=derived,
        override=override,
        effective=effective(derived, override),
        attribution=attribution,
    )


@router.get("/{learner_id}", response_model=ConfigResponse)
def get_config(
    learner_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> ConfigResponse:
    authorize_learner(learner_id, user, repos)
    return _load_config(learner_id, state, repos)


@router.put("/{learner_id}/override", response_model=ConfigResponse)
def set_override(
    learner_id: str,
    body: OverrideRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> ConfigResponse:
    authorize_learner(learner_id, user, repos)
    repos.overrides.set(learner_id, body.as_sparse_dict())
    return _load_config(learner_id, state, repos)


@router.delete("/{learner_id}/override/{param}", response_model=ConfigResponse)
def revert_override(
    learner_id: str,
    param: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> ConfigResponse:
    authorize_learner(learner_id, user, repos)
    if param not in PARAMETER_NAMES:
        raise HTTPException(status_code=400, detail=f"unknown parameter: {param}")
    repos.overrides.delete_field(learner_id, param)
    return _load_config(learner_id, state, repos)


@router.delete("/{learner_id}/override", response_model=ConfigResponse)
def reset_overrides(
    learner_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> ConfigResponse:
    authorize_learner(learner_id, user, repos)
    repos.overrides.delete_all(learner_id)
    return _load_config(learner_id, state, repos)
