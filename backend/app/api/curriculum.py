from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import AppState, get_state
from app.rag.toc import Chapter

router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])


class CurriculumResponse(BaseModel):
    chapters: list[Chapter]


@router.get("", response_model=CurriculumResponse)
def get_curriculum(state: AppState = Depends(get_state)) -> CurriculumResponse:
    return CurriculumResponse(chapters=state.curriculum)
