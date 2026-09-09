import base64
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
from app.core.mapping import derive, effective
from app.llm.client import (
    DEFAULT_MODEL,
    TUTORING_TEMPERATURE,
    TutorResponse,
    assert_configured,
    complete_turn,
    stream_turn,
)
from app.logging.turn_logger import build_turn_log
from app.rag.book_images import images_for_pages
from app.rag.retriever import format_context, retrieve
from app.rag.toc import find_chapter, format_focus
from app.store.conversations import MAX_HISTORY_MESSAGES
from app.store.users import User

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger("app.chat")


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    conversation_id: str | None = None
    attachment_ids: list[str] = []


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

    # Resolve the conversation this turn belongs to. A missing / unknown id just
    # starts a fresh thread rather than failing -- the client learns the real id
    # from the X-Conversation-Id response header.
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

    # Distinct source pages, most-relevant first (retrieve() already ranks
    # its results), for the "Quellen" links the frontend renders under the
    # reply -- independent of whether the model's prose actually cites them.
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
                model=model,
                book_context=book_context,
                history=history,
                document_texts=document_texts,
                image_data_urls=image_data_urls,
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
                conversation_id,
                body.message,
                final.text,
                book_image_refs=[(img.id, img.page) for img in book_images],
                page_refs=reference_pages,
            )
            repos.attachments.link_to_message(attachment_ids, learner_message_id)
            repos.turn_logs.append(
                build_turn_log(
                    learner_id=learner_id,
                    ruleset_version=profile.ruleset_version,
                    effective_vector=vector,
                    system_prompt=system_prompt,
                    book_context=book_context,
                    study_mode=study_mode.model_dump(),
                    conversation_id=conversation_id,
                    model=final.model,
                    temperature=TUTORING_TEMPERATURE,
                    prompt=body.message,
                    completion=final.text,
                    prompt_tokens=final.prompt_tokens,
                    completion_tokens=final.completion_tokens,
                    lesson_id=lesson.lesson_id if lesson is not None else None,
                )
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conversation_id,
            "X-Book-Image-Ids": ",".join(f"{img.id}:{img.page}" for img in book_images),
            "X-Book-Reference-Pages": ",".join(str(p) for p in reference_pages),
        },
    )


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
