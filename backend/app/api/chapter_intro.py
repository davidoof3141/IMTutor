from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import AppState, Repos, authorize_learner, get_current_user, get_repos, get_state
from app.rag.chapter_intros import intro_key, load_chapter_intros
from app.rag.toc import find_chapter
from app.store.users import User

router = APIRouter(prefix="/api/chapter-intro", tags=["chapter-intro"])

# Fixed, non-persisted trigger for scripts/generate_chapter_intros.py's
# server-initiated calls -- there is no learner message, but complete_turn()
# still needs a user-role one. What to actually say travels via book_context.
# Kept here (not in the script) so script and endpoint share one source.
INTRO_TRIGGER_MESSAGE = "Bitte gib die Einführung für dieses Kapitel."

# Single fixed instruction -- not per-value like the clause catalogue or the
# step templates, so a plain constant rather than a versioned YAML table.
INTRO_INSTRUCTION = (
    "Dies ist eine Einführungsnachricht für das gerade ausgewählte Kapitel bzw. "
    "den ausgewählten Abschnitt. Gib in 3-5 Sätzen eine kurze, einladende "
    "Übersicht darüber, worum es in diesem Teil des Lehrbuchs geht. Erkläre "
    "danach in ein bis zwei Sätzen, wie dieser Teil in den Gesamtaufbau des "
    "Buches passt (was vorher behandelt wurde, was danach folgt, wie er sich "
    "thematisch einordnet) -- nutze dafür die oben angegebene "
    "Gesamtübersicht. Stelle noch keine Verständnisfrage und beginne noch "
    "nicht mit der eigentlichen inhaltlichen Erklärung; das folgt erst, wenn "
    "die lernende Person antwortet oder eine Lektion startet."
)


class ChapterIntroResponse(BaseModel):
    text: str


@router.get("/{learner_id}", response_model=ChapterIntroResponse)
def get_chapter_intro(
    learner_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> ChapterIntroResponse:
    """Serves a pre-generated chapter/section welcome message (see
    scripts/generate_chapter_intros.py) -- a static lookup, not a model call,
    so it costs nothing at request time and is the same for every learner.
    A missing manifest entry is a 404, not a fallback live generation, so an
    incomplete build surfaces immediately instead of silently costing tokens
    on every request."""
    authorize_learner(learner_id, user, repos)
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")

    study_mode = repos.study_mode.get(learner_id)
    if study_mode.mode != "training" or study_mode.chapter_number is None:
        raise HTTPException(
            status_code=400, detail="training mode with a chapter selection is required"
        )

    chapter = find_chapter(state.curriculum, study_mode.chapter_number)
    if chapter is None:
        raise HTTPException(status_code=400, detail=f"unknown chapter: {study_mode.chapter_number}")

    key = intro_key(chapter.number, study_mode.section_number)
    text = load_chapter_intros().get(key)
    if text is None:
        raise HTTPException(status_code=404, detail="no pre-generated intro for this selection")

    return ChapterIntroResponse(text=text)
