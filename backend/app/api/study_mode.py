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
from app.rag.toc import find_chapter
from app.store.study_mode import Mode, StudyModeState
from app.store.users import User

router = APIRouter(prefix="/api/mode", tags=["mode"])


class SetModeRequest(BaseModel):
    mode: Mode
    chapter_number: str | None = None
    section_number: str | None = None


@router.get("/{learner_id}", response_model=StudyModeState)
def get_mode(
    learner_id: str,
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> StudyModeState:
    authorize_learner(learner_id, user, repos)
    return repos.study_mode.get(learner_id)


@router.put("/{learner_id}", response_model=StudyModeState)
def set_mode(
    learner_id: str,
    body: SetModeRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> StudyModeState:
    authorize_learner(learner_id, user, repos)

    chapter = None
    if body.chapter_number is not None:
        chapter = find_chapter(state.curriculum, body.chapter_number)
        if chapter is None:
            raise HTTPException(status_code=400, detail=f"unknown chapter: {body.chapter_number}")

    if body.section_number is not None and (
        chapter is None or not any(s.number == body.section_number for s in chapter.sections)
    ):
        raise HTTPException(status_code=400, detail=f"unknown section: {body.section_number}")

    new_state = StudyModeState(
        mode=body.mode,
        chapter_number=body.chapter_number,
        section_number=body.section_number,
    )
    return repos.study_mode.set(learner_id, new_state)
