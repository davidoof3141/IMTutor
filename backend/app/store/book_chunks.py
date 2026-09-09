from typing import Any

from app.store.db import Conn


def _vector_literal(embedding: list[float]) -> str:
    """pgvector's text input format, e.g. "[0.01,-0.02,...]"."""
    return "[" + ",".join(repr(x) for x in embedding) + "]"


class BookChunkRepository:
    """Chunks of the course textbook plus their embeddings, for retrieval.

    Written only by scripts/build_book_index.py (full rebuild); read only by
    app.rag.retriever at chat time.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def replace_all(self, chunks: list[tuple[str, str, int, list[float]]]) -> None:
        """Full rebuild: delete every row, insert the new set, one commit at
        the end -- so a crash mid-rebuild leaves the previous index intact
        rather than half-deleted.
        """
        self._conn.execute("DELETE FROM book_chunks")
        for chunk_id, text, page, embedding in chunks:
            self._conn.execute(
                "INSERT INTO book_chunks (chunk_id, text, page, embedding) "
                "VALUES (%s, %s, %s, %s::vector)",
                (chunk_id, text, page, _vector_literal(embedding)),
            )
        self._conn.commit()

    def search(self, query_embedding: list[float], *, k: int) -> list[dict[str, Any]]:
        """Rows ordered by ascending cosine distance (nearest first). [] if
        book_chunks is empty.
        """
        literal = _vector_literal(query_embedding)
        return self._conn.execute(
            "SELECT chunk_id, text, page, embedding <=> %s::vector AS distance "
            "FROM book_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
            (literal, literal, k),
        ).fetchall()
