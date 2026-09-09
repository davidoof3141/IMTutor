import os
from collections.abc import Iterator

from openai import OpenAI

TUTORING_TEMPERATURE = 0.7
MANIPULATION_CHECK_TEMPERATURE = 0.0

DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")


class TutorResponse:
    def __init__(self, text: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.text = text
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def assert_configured() -> None:
    """Raise before a turn starts if the LLM can't be reached at all."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY is not set")


def _client() -> OpenAI:
    assert_configured()
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )


def _messages(
    system_prompt: str,
    book_context: str,
    user_message: str,
    history: list[dict[str, str]] | None = None,
    document_texts: list[tuple[str, str]] | None = None,
    image_data_urls: list[str] | None = None,
) -> list[dict[str, object]]:
    """The message list. `book_context`, if given, is retrieved book text passed
    as its own system message -- kept separate from `system_prompt` so the
    assembled clause prompt (see core/assembler.py) stays exactly what the
    scrutability panel shows, with no free text mixed in.

    `history` is prior turns of the same conversation, already in OpenAI shape
    (`{"role": "user"|"assistant", "content": ...}`), inserted before the new
    user message so the tutor can follow the thread.

    `document_texts` is `(filename, extracted_text)` pairs for any documents
    the learner attached to this turn, each its own system message. When
    `image_data_urls` is non-empty the final user message becomes the
    OpenAI-SDK multimodal content-list form; otherwise it stays a plain
    string, so a turn with no attachments is unchanged.
    """
    messages: list[dict[str, object]] = [{"role": "system", "content": system_prompt}]
    if book_context:
        messages.append({"role": "system", "content": book_context})
    for filename, text in document_texts or []:
        messages.append(
            {"role": "system", "content": f'Angehängtes Dokument "{filename}":\n{text}'}
        )
    messages.extend(dict(m) for m in history or [])
    if image_data_urls:
        content: list[dict[str, object]] = [{"type": "text", "text": user_message}]
        content.extend(
            {"type": "image_url", "image_url": {"url": url}} for url in image_data_urls
        )
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    return messages


def complete_turn(
    *,
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    temperature: float = TUTORING_TEMPERATURE,
    book_context: str = "",
    history: list[dict[str, str]] | None = None,
    document_texts: list[tuple[str, str]] | None = None,
    image_data_urls: list[str] | None = None,
) -> TutorResponse:
    """One tutoring turn against OpenRouter. Not called from core/ -- only from api/chat.py."""
    response = _client().chat.completions.create(
        model=model,
        temperature=temperature,
        messages=_messages(  # type: ignore[arg-type]
            system_prompt, book_context, user_message, history, document_texts, image_data_urls
        ),
    )
    choice = response.choices[0]
    usage = response.usage
    return TutorResponse(
        text=choice.message.content or "",
        model=response.model,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )


def stream_turn(
    *,
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    temperature: float = TUTORING_TEMPERATURE,
    book_context: str = "",
    history: list[dict[str, str]] | None = None,
    document_texts: list[tuple[str, str]] | None = None,
    image_data_urls: list[str] | None = None,
) -> Iterator[str | TutorResponse]:
    """Same as `complete_turn`, but yields text deltas as they arrive and then a
    final `TutorResponse` carrying the full text, resolved model id and usage.
    """
    stream = _client().chat.completions.create(  # type: ignore[call-overload]
        model=model,
        temperature=temperature,
        messages=_messages(
            system_prompt, book_context, user_message, history, document_texts, image_data_urls
        ),
        stream=True,
        stream_options={"include_usage": True},
    )

    parts: list[str] = []
    final_model = model
    prompt_tokens = 0
    completion_tokens = 0

    for event in stream:
        if getattr(event, "model", None):
            final_model = event.model
        usage = getattr(event, "usage", None)
        if usage:
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
        for choice in event.choices:
            delta = choice.delta.content
            if delta:
                parts.append(delta)
                yield delta

    yield TutorResponse(
        text="".join(parts),
        model=final_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
