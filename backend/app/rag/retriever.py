"""Retrieves book passages relevant to a learner's chat message.

Not called from core/ -- only from api/chat.py. Grounding text produced here
is kept out of core/assembler.py's output: assemble() must stay pure
selection-and-concatenation over the clause catalogue, so retrieved book text
travels to the model as a separate message (see app/llm/client.py).
"""

from dataclasses import dataclass
from pathlib import Path

from app.rag.index import DEFAULT_INDEX_DIR, get_collection

DEFAULT_TOP_K = 4


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    page: int
    distance: float


def retrieve(
    query: str, *, k: int = DEFAULT_TOP_K, index_dir: Path = DEFAULT_INDEX_DIR
) -> list[RetrievedChunk]:
    """Returns the k most relevant book chunks, or [] if no index has been built yet."""
    if not index_dir.exists():
        return []
    collection = get_collection(index_dir)
    count = collection.count()
    if count == 0:
        return []
    result = collection.query(query_texts=[query], n_results=min(k, count))
    ids = result["ids"][0]
    docs = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]
    return [
        RetrievedChunk(chunk_id=chunk_id, text=doc, page=meta["page"], distance=dist)
        for chunk_id, doc, meta, dist in zip(ids, docs, metadatas, distances, strict=True)
    ]


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Formats retrieved chunks into a system message. Fixed wrapper text plus
    verbatim book excerpts -- no paraphrasing, same spirit as assemble()."""
    if not chunks:
        return ""
    lines = ["Relevante Auszüge aus dem Lehrbuch (Krcmar, Informationsmanagement):"]
    lines.extend(f"[S. {chunk.page}] {chunk.text}" for chunk in chunks)
    return "\n".join(lines)
