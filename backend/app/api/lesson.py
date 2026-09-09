import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import (
    AppState,
    Repos,
    authorize_learner,
    current_vector,
    get_current_user,
    get_repos,
    get_state,
)
from app.core.assembler import assemble
from app.core.constants import CURRENT_PLANNER_VERSION
from app.core.planner import CurriculumSelection, LessonStep, PlanRationale, plan_lesson
from app.core.profile import Profile
from app.core.step_templates import format_step
from app.core.vector import ControlVector
from app.llm.client import (
    DEFAULT_MODEL,
    TUTORING_TEMPERATURE,
    TutorResponse,
    assert_configured,
    complete_turn,
)
from app.logging.turn_logger import build_turn_log
from app.rag.toc import find_chapter, format_focus
from app.store.conversations import MAX_HISTORY_MESSAGES
from app.store.lessons import LessonPlan, LessonStatus, StoredLessonPlan
from app.store.users import User

router = APIRouter(prefix="/api/lesson", tags=["lesson"])

# Fixed, non-persisted trigger for a server-initiated step turn -- there is
# no learner message to send, but complete_turn() still needs a user-role
# message. The actual instruction content travels via book_context (see
# _run_step), same as the rest of this endpoint's non-goals require.
STEP_TRIGGER_MESSAGE = "Bitte fahre mit dem nächsten Lektionsschritt fort."


class LessonResponse(BaseModel):
    plan: LessonPlan
    rationale: PlanRationale
    current_step: int
    status: LessonStatus
    vector_drifted: bool
    # The tutor's message for the step just run; absent on a plain GET.
    message: str | None = None


def _to_response(
    stored: StoredLessonPlan, *, vector_drifted: bool, message: str | None = None
) -> LessonResponse:
    plan = LessonPlan(
        lesson_id=stored.lesson_id,
        learner_id=stored.learner_id,
        conversation_id=stored.conversation_id,
        ruleset_version=stored.ruleset_version,
        planner_version=stored.planner_version,
        chapter_ref=stored.chapter_ref,
        section_ref=stored.section_ref,
        vector_snapshot=stored.vector_snapshot,
        steps=stored.steps,
        created_at=stored.created_at,
    )
    return LessonResponse(
        plan=plan,
        rationale=stored.rationale,
        current_step=stored.current_step,
        status=stored.status,
        vector_drifted=vector_drifted,
        message=message,
    )


def _get_owned_plan(conversation_id: str, repos: Repos, user: User) -> StoredLessonPlan:
    plan = repos.lessons.get_by_conversation(conversation_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="lesson not found")
    authorize_learner(plan.learner_id, user, repos)
    return plan


def _run_step(
    plan: StoredLessonPlan, step: LessonStep, *, profile: Profile, state: AppState, repos: Repos
) -> tuple[TutorResponse, str, str, ControlVector, str]:
    """Runs one lesson-step turn against the model. Returns
    (response, system_prompt, book_context, vector, model) -- the caller
    persists the message and writes the turn log with them."""
    catalogue = state.catalogues[profile.ruleset_version]
    vector = current_vector(profile, state, repos)
    system_prompt = assemble(vector, catalogue)

    chapter = find_chapter(state.curriculum, plan.chapter_ref)
    if chapter is None:
        raise HTTPException(status_code=400, detail=f"unknown chapter: {plan.chapter_ref}")
    section = None
    if plan.section_ref is not None:
        section = next((s for s in chapter.sections if s.number == plan.section_ref), None)
    focus = format_focus(chapter, section)

    if plan.planner_version not in state.step_templates:
        raise HTTPException(
            status_code=500, detail=f"unknown planner version: {plan.planner_version}"
        )
    instruction = format_step(step, state.step_templates[plan.planner_version])
    book_context = f"{focus}\n\n{instruction}"

    history = [
        {"role": "user" if m.role == "learner" else "assistant", "content": m.text}
        for m in repos.conversations.messages(plan.conversation_id, limit=MAX_HISTORY_MESSAGES)
    ]

    model = repos.sessions.get_or_create(profile.learner_id, DEFAULT_MODEL)
    try:
        assert_configured()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response = complete_turn(
        system_prompt=system_prompt,
        user_message=STEP_TRIGGER_MESSAGE,
        model=model,
        book_context=book_context,
        history=history,
    )
    return response, system_prompt, book_context, vector, model


def _log_step_turn(
    *,
    repos: Repos,
    profile: Profile,
    vector: ControlVector,
    system_prompt: str,
    book_context: str,
    conversation_id: str,
    response: TutorResponse,
    lesson_id: str,
    step: LessonStep,
) -> None:
    repos.turn_logs.append(
        build_turn_log(
            learner_id=profile.learner_id,
            ruleset_version=profile.ruleset_version,
            effective_vector=vector,
            system_prompt=system_prompt,
            book_context=book_context,
            conversation_id=conversation_id,
            model=response.model,
            temperature=TUTORING_TEMPERATURE,
            prompt=book_context,
            completion=response.text,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            lesson_id=lesson_id,
            step_index=step.index,
            step_kind=step.kind,
        )
    )


@router.post("/{learner_id}", response_model=LessonResponse, status_code=201)
def create_lesson(
    learner_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> LessonResponse:
    """Plans a lesson for the learner's current training-mode selection, then
    runs its first step as a server-initiated turn -- the learner lands on a
    thread that already has content, no message required from them."""
    authorize_learner(learner_id, user, repos)
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")

    study_mode = repos.study_mode.get(learner_id)
    if study_mode.mode != "training" or study_mode.chapter_number is None:
        raise HTTPException(
            status_code=400, detail="training mode with a chapter selection is required"
        )
    selection = CurriculumSelection(
        chapter_number=study_mode.chapter_number, section_number=study_mode.section_number
    )

    if CURRENT_PLANNER_VERSION not in state.planner_tables:
        raise HTTPException(status_code=500, detail="no planner table configured")
    planner_table = state.planner_tables[CURRENT_PLANNER_VERSION]

    vector = current_vector(profile, state, repos)
    try:
        steps, rationale = plan_lesson(vector, selection, state.curriculum, planner_table)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conversation = repos.conversations.create(learner_id, study_mode)
    lesson_id = str(uuid.uuid4())
    stored = repos.lessons.create(
        lesson_id=lesson_id,
        learner_id=learner_id,
        conversation_id=conversation.id,
        ruleset_version=profile.ruleset_version,
        planner_version=planner_table.version,
        chapter_ref=selection.chapter_number,
        section_ref=selection.section_number,
        vector_snapshot=vector,
        steps=steps,
        rationale=rationale,
    )

    response, system_prompt, book_context, run_vector, _ = _run_step(
        stored, stored.steps[0], profile=profile, state=state, repos=repos
    )
    repos.conversations.add_tutor_message(conversation.id, response.text)
    _log_step_turn(
        repos=repos,
        profile=profile,
        vector=run_vector,
        system_prompt=system_prompt,
        book_context=book_context,
        conversation_id=conversation.id,
        response=response,
        lesson_id=lesson_id,
        step=stored.steps[0],
    )

    return _to_response(stored, vector_drifted=False, message=response.text)


@router.get("/{conversation_id}", response_model=LessonResponse)
def get_lesson(
    conversation_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> LessonResponse:
    plan = _get_owned_plan(conversation_id, repos, user)
    profile = repos.profiles.get(plan.learner_id)
    assert profile is not None  # the plan couldn't exist without one
    drifted = current_vector(profile, state, repos) != plan.vector_snapshot
    return _to_response(plan, vector_drifted=drifted)


@router.post("/{conversation_id}/advance", response_model=LessonResponse)
def advance_lesson(
    conversation_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> LessonResponse:
    """Runs the next step's turn. Free-text messages in the thread are
    ordinary tutoring turns (app/api/chat.py) and never call this -- the
    pointer only moves on an explicit advance."""
    plan = _get_owned_plan(conversation_id, repos, user)
    if plan.status != "active":
        raise HTTPException(status_code=409, detail=f"lesson is {plan.status}, not active")
    if plan.current_step >= len(plan.steps) - 1:
        raise HTTPException(status_code=409, detail="lesson has no further steps")

    profile = repos.profiles.get(plan.learner_id)
    assert profile is not None
    next_step = plan.steps[plan.current_step + 1]

    response, system_prompt, book_context, vector, _ = _run_step(
        plan, next_step, profile=profile, state=state, repos=repos
    )
    repos.conversations.add_tutor_message(plan.conversation_id, response.text)
    _log_step_turn(
        repos=repos,
        profile=profile,
        vector=vector,
        system_prompt=system_prompt,
        book_context=book_context,
        conversation_id=plan.conversation_id,
        response=response,
        lesson_id=plan.lesson_id,
        step=next_step,
    )

    updated = repos.lessons.advance(plan.lesson_id)
    assert updated is not None
    drifted = current_vector(profile, state, repos) != plan.vector_snapshot
    return _to_response(updated, vector_drifted=drifted, message=response.text)


@router.post("/{conversation_id}/abandon", response_model=LessonResponse)
def abandon_lesson(
    conversation_id: str,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> LessonResponse:
    plan = _get_owned_plan(conversation_id, repos, user)
    updated = repos.lessons.abandon(plan.lesson_id)
    assert updated is not None
    profile = repos.profiles.get(plan.learner_id)
    assert profile is not None
    drifted = current_vector(profile, state, repos) != plan.vector_snapshot
    return _to_response(updated, vector_drifted=drifted)
