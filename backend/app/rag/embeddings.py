"""Text embeddings via OpenRouter -- replaces the old local sentence-transformers
model so the app has no local ML dependency (see app/llm/client.py for the
matching chat-completions client this mirrors).
"""

import os

from openai import OpenAI

DEFAULT_EMBEDDING_MODEL = os.environ.get("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536


def assert_configured() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY is not set")


def _client() -> OpenAI:
    assert_configured()
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )


def embed_texts(texts: list[str], *, model: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    """Embeds a batch of texts in one call, order-preserving."""
    response = _client().embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


def embed_query(text: str, *, model: str = DEFAULT_EMBEDDING_MODEL) -> list[float]:
    return embed_texts([text], model=model)[0]
