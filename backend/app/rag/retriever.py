"""Retrieves book passages relevant to a learner's chat message.

Not called from core/ -- only from api/chat.py. Grounding text produced here
is kept out of core/assembler.py's output: assemble() must stay pure
selection-and-concatenation over the clause catalogue, so retrieved book text
travels to the model as a separate message (see app/llm/client.py).
"""

from dataclasses import dataclass

from app.rag.embeddings import embed_query
from app.store.book_chunks import BookChunkRepository
from app.store.db import connection

DEFAULT_TOP_K = 4


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    page: int
    distance: float


def retrieve(query: str, *, k: int = DEFAULT_TOP_K) -> list[RetrievedChunk]:
    """Returns the k most relevant book chunks, or [] if none have been indexed yet."""
    query_embedding = embed_query(query)
    with connection() as conn:
        rows = BookChunkRepository(conn).search(query_embedding, k=k)
    return [
        RetrievedChunk(chunk_id=r["chunk_id"], text=r["text"], page=r["page"], distance=r["distance"])
        for r in rows
    ]


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Formats retrieved chunks into a system message. Fixed wrapper text plus
    verbatim book excerpts -- no paraphrasing, same spirit as assemble()."""
    if not chunks:
        return ""
    lines = ["Relevante Auszüge aus dem Lehrbuch (Krcmar, Informationsmanagement):"]
    lines.extend(f"[S. {chunk.page}] {chunk.text}" for chunk in chunks)
    return "\n".join(lines)
