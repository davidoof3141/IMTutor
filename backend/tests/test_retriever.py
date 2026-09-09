import pytest

from app.rag.retriever import RetrievedChunk, format_context, retrieve
from app.store.db import Conn


def test_retrieve_returns_empty_when_no_chunks_indexed(
    db_conn: Conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.rag.retriever.embed_query", lambda text: [0.0] * 1536)
    assert retrieve("what is information management?") == []


def test_format_context_of_no_chunks_is_empty_string() -> None:
    assert format_context([]) == ""


def test_format_context_includes_page_numbers_and_text() -> None:
    chunks = [
        RetrievedChunk(chunk_id="book-p12-0", text="Informationsmanagement umfasst...", page=12, distance=0.1),
        RetrievedChunk(chunk_id="book-p13-0", text="Ein weiterer Aspekt...", page=13, distance=0.2),
    ]
    context = format_context(chunks)
    assert "[S. 12] Informationsmanagement umfasst..." in context
    assert "[S. 13] Ein weiterer Aspekt..." in context
