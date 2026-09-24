import base64
import json
import logging
import random
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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
from app.core.mapping import derive, effective
from app.core.vector import ControlVector
from app.llm.client import (
    DEFAULT_MODEL,
    TUTORING_TEMPERATURE,
    TutorResponse,
    assert_configured,
    complete_turn,
    stream_turn,
)
from app.logging.turn_logger import build_turn_log
from app.rag.book_images import BookImageMeta, images_for_pages
from app.rag.retriever import format_context, retrieve
from app.rag.toc import find_chapter, format_focus
from app.store.comparisons import ReasonTag, VariantKind, VariantLabel
from app.store.conversations import MAX_HISTORY_MESSAGES
from app.store.study_mode import StudyModeState
from app.store.users import User

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger("app.chat")


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    conversation_id: str | None = None
    attachment_ids: list[str] = []


@dataclass
class _TurnSetup:
    """Everything a turn needs that doesn't depend on which variant(s) of the
    reply get generated -- shared by the single-answer and comparison chat
    endpoints so the conversation/attachments/retrieval bookkeeping is only
    written once."""

    conversation_id: str
    attachment_ids: list[str]
    image_data_urls: list[str]
    document_texts: list[tuple[str, str]]
    history: list[dict[str, str]]
    book_context: str
    book_images: list[BookImageMeta]
    reference_pages: list[int]
    model: str
    lesson_id: str | None


def _prepare_turn(
    learner_id: str,
    body: ChatRequest,
    state: AppState,
    repos: Repos,
    study_mode: StudyModeState,
) -> _TurnSetup:
    conversation = None
    if body.conversation_id is not None:
        conversation = repos.conversations.get(body.conversation_id)
        if conversation is not None and conversation.learner_id != learner_id:
            conversation = None
    if conversation is None:
        conversation = repos.conversations.create(learner_id, study_mode)
    conversation_id = conversation.id

    resolved_attachments = repos.attachments.resolve_for_chat(
        body.attachment_ids, learner_id, conversation_id
    )
    attachment_ids = [a.id for a in resolved_attachments]
    image_data_urls = [
        f"data:{a.mime_type};base64,{base64.b64encode(a.data).decode()}"
        for a in resolved_attachments
        if a.kind == "image"
    ]
    document_texts = [
        (a.filename, a.extracted_text or "")
        for a in resolved_attachments
        if a.kind == "document"
    ]

    history = [
        {"role": "user" if m.role == "learner" else "assistant", "content": m.text}
        for m in repos.conversations.messages(conversation_id, limit=MAX_HISTORY_MESSAGES)
    ]

    context_parts: list[str] = []
    if study_mode.mode == "training" and study_mode.chapter_number:
        chapter = find_chapter(state.curriculum, study_mode.chapter_number)
        if chapter is not None:
            section = next(
                (s for s in chapter.sections if s.number == study_mode.section_number), None
            )
            context_parts.append(format_focus(chapter, section))
    retrieved = retrieve(body.message)
    retrieved_context = format_context(retrieved)
    if retrieved_context:
        context_parts.append(retrieved_context)
    book_context = "\n\n".join(context_parts)

    book_images = images_for_pages([c.page for c in retrieved])
    reference_pages: list[int] = []
    for c in retrieved:
        if c.page not in reference_pages:
            reference_pages.append(c.page)

    # The model is pinned on the learner's first turn (see SessionRepository) so
    # a session's configuration stays reproducible. `body.model` only takes
    # effect for that first turn.
    model = repos.sessions.get_or_create(learner_id, body.model or DEFAULT_MODEL)

    # A free-text message in a lesson thread still tags the turn log with the
    # lesson it belongs to, just with no step_index/step_kind -- only
    # app/api/lesson.py's driven turns set those (see build_turn_log).
    lesson = repos.lessons.get_by_conversation(conversation_id)

    return _TurnSetup(
        conversation_id=conversation_id,
        attachment_ids=attachment_ids,
        image_data_urls=image_data_urls,
        document_texts=document_texts,
        history=history,
        book_context=book_context,
        book_images=book_images,
        reference_pages=reference_pages,
        model=model,
        lesson_id=lesson.lesson_id if lesson is not None else None,
    )


def _response_headers(setup: _TurnSetup) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Conversation-Id": setup.conversation_id,
        "X-Book-Image-Ids": ",".join(f"{img.id}:{img.page}" for img in setup.book_images),
        "X-Book-Reference-Pages": ",".join(str(p) for p in setup.reference_pages),
    }


@router.post("/{learner_id}")
def chat(
    learner_id: str,
    body: ChatRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Streams the tutor's reply as plain-text deltas (`text/plain`).

    All checks that can fail — auth, the learner, the LLM being configured —
    run before the stream starts, so the client still sees a proper 4xx/503.
    The turn log is written once the stream completes.
    """
    authorize_learner(learner_id, user, repos)
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")

    ruleset = state.rulesets[profile.ruleset_version]
    catalogue = state.catalogues[profile.ruleset_version]
    derived, _ = derive(profile, ruleset)
    override = repos.overrides.get(learner_id)
    vector = effective(derived, override)
    system_prompt = assemble(vector, catalogue)

    study_mode = repos.study_mode.get(learner_id)
    setup = _prepare_turn(learner_id, body, state, repos, study_mode)

    try:
        assert_configured()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    def event_stream() -> Iterator[str]:
        final: TutorResponse | None = None
        try:
            for piece in stream_turn(
                system_prompt=system_prompt,
                user_message=body.message,
                model=setup.model,
                book_context=setup.book_context,
                history=setup.history,
                document_texts=setup.document_texts,
                image_data_urls=setup.image_data_urls,
            ):
                if isinstance(piece, str):
                    yield piece
                else:
                    final = piece
        except Exception:
            # The stream has already started, so the status code is fixed at 200;
            # log server-side and surface the failure inline to the learner.
            logger.exception("chat stream failed for learner %s", learner_id)
            yield "\n\n⚠️ Die Antwort konnte nicht abgerufen werden."
            return

        if final is not None:
            learner_message_id = repos.conversations.add_turn(
                setup.conversation_id,
                body.message,
                final.text,
                book_image_refs=[(img.id, img.page) for img in setup.book_images],
                page_refs=setup.reference_pages,
            )
            repos.attachments.link_to_message(setup.attachment_ids, learner_message_id)
            repos.turn_logs.append(
                build_turn_log(
                    learner_id=learner_id,
                    ruleset_version=profile.ruleset_version,
                    effective_vector=vector,
                    system_prompt=system_prompt,
                    book_context=setup.book_context,
                    study_mode=study_mode.model_dump(),
                    conversation_id=setup.conversation_id,
                    model=final.model,
                    temperature=TUTORING_TEMPERATURE,
                    prompt=body.message,
                    completion=final.text,
                    prompt_tokens=final.prompt_tokens,
                    completion_tokens=final.completion_tokens,
                    lesson_id=setup.lesson_id,
                )
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/plain; charset=utf-8",
        headers=_response_headers(setup),
    )


def _interleaved_stream(
    prompts: dict[VariantLabel, str],
    *,
    user_message: str,
    model: str,
    book_context: str,
    history: list[dict[str, str]],
    document_texts: list[tuple[str, str]],
    image_data_urls: list[str],
) -> Iterator[tuple[VariantLabel, str | TutorResponse]]:
    """Runs every variant's completion concurrently (each is a blocking,
    synchronous stream against OpenRouter) and yields `(label, piece)` as
    pieces arrive from whichever variant produced one next -- text deltas in
    real arrival order, then one final `TutorResponse` per label. A variant
    whose call fails still gets a (short, visible) final response rather than
    taking the whole comparison down with it."""
    labels = list(prompts.keys())
    q: Queue[tuple[VariantLabel, str | TutorResponse]] = Queue()

    def run(label: VariantLabel) -> None:
        try:
            for piece in stream_turn(
                system_prompt=prompts[label],
                user_message=user_message,
                model=model,
                book_context=book_context,
                history=history,
                document_texts=document_texts,
                image_data_urls=image_data_urls,
            ):
                q.put((label, piece))
        except Exception:
            logger.exception("comparison stream failed for variant %s", label)
            warning = "⚠️ Diese Antwort konnte nicht abgerufen werden."
            q.put((label, warning))
            q.put((label, TutorResponse(text=warning, model=model, prompt_tokens=0, completion_tokens=0)))

    with ThreadPoolExecutor(max_workers=len(labels)) as pool:
        futures = [pool.submit(run, label) for label in labels]
        finished = 0
        while finished < len(labels):
            label, piece = q.get()
            yield label, piece
            if isinstance(piece, TutorResponse):
                finished += 1
        for future in futures:
            future.result()


@router.post("/{learner_id}/compare")
def compare(
    learner_id: str,
    body: ChatRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Dual-answer variant of `chat()` for link-invited accounts: streams two
    replies to the same message side by side -- one personalized (the
    learner's usual effective vector), one generic (the rule set's plain
    defaults) -- randomly assigned to slots "a"/"b" each turn so on-screen
    position carries no signal about which is which.

    Neither reply is added to the conversation yet; the body is a stream of
    newline-delimited `{"variant": "a"|"b", "delta": str}` /
    `{"variant": "a"|"b", "done": true}` events. The learner's pick (see
    `choose_comparison` below) is what actually appends a turn.
    """
    if not user.has_login_link:
        raise HTTPException(
            status_code=403, detail="comparison mode is not enabled for this account"
        )

    authorize_learner(learner_id, user, repos)
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")

    ruleset = state.rulesets[profile.ruleset_version]
    catalogue = state.catalogues[profile.ruleset_version]
    derived, _ = derive(profile, ruleset)
    override = repos.overrides.get(learner_id)
    personalized_vector = effective(derived, override)
    baseline_vector = ControlVector.model_validate(ruleset.defaults)

    variant_kinds: list[VariantKind] = ["personalized", "generic"]
    random.shuffle(variant_kinds)
    variant_a_kind, variant_b_kind = variant_kinds
    vector_by_kind = {"personalized": personalized_vector, "generic": baseline_vector}
    prompts: dict[VariantLabel, str] = {
        "a": assemble(vector_by_kind[variant_a_kind], catalogue),
        "b": assemble(vector_by_kind[variant_b_kind], catalogue),
    }

    study_mode = repos.study_mode.get(learner_id)
    setup = _prepare_turn(learner_id, body, state, repos, study_mode)

    try:
        assert_configured()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    comparison_id = repos.comparisons.create_pending(
        conversation_id=setup.conversation_id,
        learner_id=learner_id,
        learner_message=body.message,
        ruleset_version=profile.ruleset_version,
        personalized_vector=personalized_vector.model_dump(),
        baseline_vector=baseline_vector.model_dump(),
        variant_a_kind=variant_a_kind,
        variant_b_kind=variant_b_kind,
        book_context=setup.book_context,
        book_image_refs=[(img.id, img.page) for img in setup.book_images],
        page_refs=setup.reference_pages,
        attachment_ids=setup.attachment_ids,
        lesson_id=setup.lesson_id,
        study_mode=study_mode.model_dump(),
    )

    def event_stream() -> Iterator[str]:
        for label, piece in _interleaved_stream(
            prompts,
            user_message=body.message,
            model=setup.model,
            book_context=setup.book_context,
            history=setup.history,
            document_texts=setup.document_texts,
            image_data_urls=setup.image_data_urls,
        ):
            if isinstance(piece, str):
                yield json.dumps({"variant": label, "delta": piece}) + "\n"
            else:
                repos.comparisons.record_variant_result(
                    comparison_id,
                    label,
                    text=piece.text,
                    model=piece.model,
                    prompt_tokens=piece.prompt_tokens,
                    completion_tokens=piece.completion_tokens,
                )
                yield json.dumps({"variant": label, "done": True}) + "\n"

    headers = _response_headers(setup)
    headers["X-Comparison-Id"] = comparison_id
    return StreamingResponse(event_stream(), media_type="application/x-ndjson", headers=headers)


class ChooseComparisonRequest(BaseModel):
    variant: VariantLabel
    reasons: list[ReasonTag] = Field(min_length=1, max_length=6)
    other_reason: str | None = Field(default=None, max_length=500)


class ChooseComparisonResponse(BaseModel):
    conversation_id: str


@router.post(
    "/{learner_id}/compare/{comparison_id}/choose", response_model=ChooseComparisonResponse
)
def choose_comparison(
    learner_id: str,
    comparison_id: str,
    body: ChooseComparisonRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> ChooseComparisonResponse:
    """Records the learner's pick and reason(s), then turns the chosen
    variant into the actual conversation turn -- the other variant stays on
    the comparison row for evaluation but never enters the conversation
    history the tutor sees on later turns."""
    authorize_learner(learner_id, user, repos)

    row = repos.comparisons.get_pending(comparison_id, learner_id)
    if row is None:
        raise HTTPException(status_code=404, detail="comparison not found or already decided")

    chosen_text = row[f"variant_{body.variant}_text"]
    if chosen_text is None:
        raise HTTPException(
            status_code=409, detail="that variant has not finished generating yet"
        )
    if "other" in body.reasons and not (body.other_reason and body.other_reason.strip()):
        raise HTTPException(
            status_code=400, detail="other_reason is required when 'other' is selected"
        )

    repos.comparisons.finalize(
        comparison_id,
        chosen_variant=body.variant,
        reasons=body.reasons,
        other_reason=body.other_reason,
    )

    book_image_refs = [(pair[0], pair[1]) for pair in row["book_image_refs"]]
    learner_message_id = repos.conversations.add_turn(
        row["conversation_id"],
        row["learner_message"],
        chosen_text,
        book_image_refs=book_image_refs,
        page_refs=row["page_refs"],
    )
    repos.attachments.link_to_message(row["attachment_ids"], learner_message_id)

    chosen_kind = row[f"variant_{body.variant}_kind"]
    chosen_vector_json = (
        row["personalized_vector"] if chosen_kind == "personalized" else row["baseline_vector"]
    )
    chosen_vector = ControlVector.model_validate(chosen_vector_json)
    catalogue = state.catalogues[row["ruleset_version"]]
    system_prompt = assemble(chosen_vector, catalogue)

    repos.turn_logs.append(
        build_turn_log(
            learner_id=learner_id,
            ruleset_version=row["ruleset_version"],
            effective_vector=chosen_vector,
            system_prompt=system_prompt,
            book_context=row["book_context"],
            study_mode=row["study_mode"],
            conversation_id=row["conversation_id"],
            model=row[f"variant_{body.variant}_model"],
            temperature=TUTORING_TEMPERATURE,
            prompt=row["learner_message"],
            completion=chosen_text,
            prompt_tokens=row[f"variant_{body.variant}_prompt_tokens"] or 0,
            completion_tokens=row[f"variant_{body.variant}_completion_tokens"] or 0,
            lesson_id=row["lesson_id"],
        )
    )

    return ChooseComparisonResponse(conversation_id=row["conversation_id"])


class SuggestionsRequest(BaseModel):
    conversation_id: str


class SuggestionsResponse(BaseModel):
    questions: list[str]


# Fixed, non-persisted trigger -- same reasoning as app/api/lesson.py's
# STEP_TRIGGER_MESSAGE: there is no new learner message here, but
# complete_turn() still needs a user-role one. What to actually do travels
# via book_context.
SUGGESTIONS_TRIGGER_MESSAGE = "Bitte schlage passende Rückfragen vor."

SUGGESTIONS_INSTRUCTION = (
    "Schlage genau drei kurze Rückfragen vor, die die lernende Person als "
    "Nächstes stellen könnte, ausgehend vom bisherigen Gesprächsverlauf. "
    "Formuliere sie aus der Sicht der lernenden Person -- als Frage an dich, "
    "den Tutor --, auf Deutsch, jede höchstens ein kurzer Satz. Antworte mit "
    "genau drei Zeilen: eine Frage pro Zeile, ohne Nummerierung, "
    "Aufzählungszeichen oder sonstigen Text."
)


@router.post("/{learner_id}/suggestions", response_model=SuggestionsResponse)
def get_suggestions(
    learner_id: str,
    body: SuggestionsRequest,
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> SuggestionsResponse:
    """Three candidate follow-up questions for the chips above the chat
    input, generated fresh from the conversation so far -- unlike the
    chapter intro, this can't be pre-generated (it depends on what was just
    said), so it stays a live call. Not persisted as a message; logged to
    the turn log like any other model call, for the same reproducibility
    reason."""
    authorize_learner(learner_id, user, repos)
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")

    conversation = repos.conversations.get(body.conversation_id)
    if conversation is None or conversation.learner_id != learner_id:
        raise HTTPException(status_code=404, detail="conversation not found")

    catalogue = state.catalogues[profile.ruleset_version]
    vector = current_vector(profile, state, repos)
    system_prompt = assemble(vector, catalogue)

    history = [
        {"role": "user" if m.role == "learner" else "assistant", "content": m.text}
        for m in repos.conversations.messages(body.conversation_id, limit=MAX_HISTORY_MESSAGES)
    ]
    if not history:
        raise HTTPException(status_code=400, detail="conversation has no messages yet")

    model = repos.sessions.get_or_create(learner_id, DEFAULT_MODEL)
    try:
        assert_configured()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response = complete_turn(
        system_prompt=system_prompt,
        user_message=SUGGESTIONS_TRIGGER_MESSAGE,
        model=model,
        book_context=SUGGESTIONS_INSTRUCTION,
        history=history,
    )
    questions = [line.strip(" -*\t") for line in response.text.splitlines() if line.strip()][:3]

    repos.turn_logs.append(
        build_turn_log(
            learner_id=learner_id,
            ruleset_version=profile.ruleset_version,
            effective_vector=vector,
            system_prompt=system_prompt,
            book_context=SUGGESTIONS_INSTRUCTION,
            conversation_id=body.conversation_id,
            model=response.model,
            temperature=TUTORING_TEMPERATURE,
            prompt=SUGGESTIONS_INSTRUCTION,
            completion=response.text,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )
    )

    return SuggestionsResponse(questions=questions)
