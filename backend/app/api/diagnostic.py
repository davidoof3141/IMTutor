"""Per-chapter rapid diagnostic (runs BEFORE instruction; DR1, DR6).

Keyed by the learner's current training-mode selection, so the client never
has to compute diagnostic keys. The answer key never leaves the server.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.config import OverrideRequest
from app.api.deps import (
    AppState,
    Repos,
    authorize_learner,
    get_current_user,
    get_repos,
    get_state,
    resolve_config,
)
from app.core.constants import PARAMETER_NAMES
from app.core.diagnostic import Diagnostic, resolve_diagnostic, score
from app.core.profile import PriorKnowledge, Profile
from app.core.vector import Attribution, ControlVector, Override
from app.store.chapter_diagnostics import DiagnosticAlreadyTaken, StoredDiagnostic
from app.store.users import User

router = APIRouter(prefix="/api/diagnostic", tags=["diagnostic"])


# The file stores the English sentinel; learners see this.
DONT_KNOW_LABEL = "Ich weiß es nicht"


class PublicOption(BaseModel):
    text: str


class PublicItem(BaseModel):
    stem: str
    options: list[PublicOption]  # no `correct` / `dont_know` flags: no answer key


class DiagnosticResult(BaseModel):
    diagnostic_key: str
    correct_count: int
    item_count: int
    experience_seed: PriorKnowledge
    prior_knowledge: PriorKnowledge  # chapter-level; replaced the seed for this chapter only
    derived: ControlVector
    attribution: Attribution
    override: Override
    effective: ControlVector


class DiagnosticStatus(BaseModel):
    required: bool  # an authored diagnostic covers the current selection
    key: str | None = None
    items: list[PublicItem] = []
    result: DiagnosticResult | None = None


class AnswersRequest(BaseModel):
    answers: list[int]


def _selected_diagnostic(learner_id: str, state: AppState, repos: Repos) -> Diagnostic | None:
    mode = repos.study_mode.get(learner_id)
    if mode.mode != "training" or mode.chapter_number is None:
        return None
    return resolve_diagnostic(state.diagnostics, mode.chapter_number)


def _result(
    profile: Profile, diagnostic: Diagnostic, state: AppState, repos: Repos
) -> DiagnosticResult:
    stored = repos.chapter_diagnostics.get(profile.learner_id, diagnostic.chapter_id)
    assert stored is not None
    resolved = resolve_config(profile, state, repos)
    return DiagnosticResult(
        diagnostic_key=stored.diagnostic_key,
        correct_count=stored.correct_count,
        item_count=len(diagnostic.items),
        experience_seed=stored.experience_seed,
        prior_knowledge=stored.prior_knowledge,
        derived=resolved.derived,
        attribution=resolved.attribution,
        override=resolved.override,
        effective=resolved.effective,
    )


def _load(
    learner_id: str, state: AppState, repos: Repos, user: User
) -> tuple[Profile, Diagnostic]:
    authorize_learner(learner_id, user, repos)
    profile = repos.profiles.get(learner_id)
    assert profile is not None  # authorize_learner 404s otherwise
    diagnostic = _selected_diagnostic(learner_id, state, repos)
    if diagnostic is None:
        raise HTTPException(status_code=404, detail="no diagnostic for the current selection")
    return profile, diagnostic


@router.get("/{learner_id}", response_model=DiagnosticStatus)
def get_status(
    learner_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> DiagnosticStatus:
    authorize_learner(learner_id, user, repos)
    profile = repos.profiles.get(learner_id)
    assert profile is not None
    diagnostic = _selected_diagnostic(learner_id, state, repos)
    if diagnostic is None:
        return DiagnosticStatus(required=False)
    items = [
        PublicItem(
            stem=i.stem,
            options=[
                PublicOption(text=DONT_KNOW_LABEL if o.dont_know else o.text) for o in i.options
            ],
        )
        for i in diagnostic.items
    ]
    if repos.chapter_diagnostics.get(learner_id, diagnostic.chapter_id) is None:
        return DiagnosticStatus(required=True, key=diagnostic.chapter_id, items=items)
    return DiagnosticStatus(
        required=True,
        key=diagnostic.chapter_id,
        items=items,
        result=_result(profile, diagnostic, state, repos),
    )


@router.post("/{learner_id}", response_model=DiagnosticResult, status_code=201)
def submit(
    learner_id: str,
    body: AnswersRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> DiagnosticResult:
    profile, diagnostic = _load(learner_id, state, repos, user)
    try:
        count, level = score(
            diagnostic, body.answers, profile.prior_knowledge_seed, state.scoring_table
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        repos.chapter_diagnostics.create(
            StoredDiagnostic(
                learner_id=learner_id,
                diagnostic_key=diagnostic.chapter_id,
                answers=body.answers,
                correct_count=count,
                experience_seed=profile.prior_knowledge_seed,
                prior_knowledge=level,
                override={},
            )
        )
    except DiagnosticAlreadyTaken as exc:
        raise HTTPException(status_code=409, detail="diagnostic already taken") from exc
    return _result(profile, diagnostic, state, repos)


def _chapter_override(learner_id: str, key: str, repos: Repos) -> Override:
    stored = repos.chapter_diagnostics.get(learner_id, key)
    if stored is None:
        raise HTTPException(status_code=409, detail="take the diagnostic first")
    return dict(stored.override)


@router.put("/{learner_id}/override", response_model=DiagnosticResult)
def set_override(
    learner_id: str,
    body: OverrideRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> DiagnosticResult:
    profile, diagnostic = _load(learner_id, state, repos, user)
    current = _chapter_override(learner_id, diagnostic.chapter_id, repos)
    before = resolve_config(profile, state, repos)
    for field, new_value in body.as_sparse_dict().items():
        old_value = before.effective.model_dump()[field]
        if old_value != new_value:
            repos.override_changes.log(learner_id, field, old_value, new_value)
    repos.chapter_diagnostics.set_override(
        learner_id, diagnostic.chapter_id, {**current, **body.as_sparse_dict()}
    )
    return _result(profile, diagnostic, state, repos)


@router.delete("/{learner_id}/override/{param}", response_model=DiagnosticResult)
def revert_override(
    learner_id: str,
    param: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> DiagnosticResult:
    if param not in PARAMETER_NAMES:
        raise HTTPException(status_code=400, detail=f"unknown parameter: {param}")
    profile, diagnostic = _load(learner_id, state, repos, user)
    current = _chapter_override(learner_id, diagnostic.chapter_id, repos)
    if param in current:
        before = resolve_config(profile, state, repos)
        repos.override_changes.log(
            learner_id, param, current[param], getattr(before.derived, param)
        )
        del current[param]
        repos.chapter_diagnostics.set_override(learner_id, diagnostic.chapter_id, current)
    return _result(profile, diagnostic, state, repos)


@router.delete("/{learner_id}/override", response_model=DiagnosticResult)
def reset_override(
    learner_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> DiagnosticResult:
    profile, diagnostic = _load(learner_id, state, repos, user)
    current = _chapter_override(learner_id, diagnostic.chapter_id, repos)
    before = resolve_config(profile, state, repos)
    for field, old_value in current.items():
        repos.override_changes.log(learner_id, field, old_value, getattr(before.derived, field))
    repos.chapter_diagnostics.set_override(learner_id, diagnostic.chapter_id, {})
    return _result(profile, diagnostic, state, repos)
