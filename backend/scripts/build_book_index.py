"""Rebuilds the pgvector index over the course textbook.

Run after the book PDF changes, or once before the first chat request:

    uv run python scripts/build_book_index.py

Targets whatever DATABASE_URL points at -- run it against the production
database to (re)index production; there is no local persistent volume to
manage anymore.
"""

from app.rag.chunking import BOOK_PATH, chunk_book
from app.rag.embeddings import embed_texts
from app.store.book_chunks import BookChunkRepository
from app.store.db import connection, init_db

EMBED_BATCH_SIZE = 100


def main() -> None:
    init_db()

    chunks = chunk_book(BOOK_PATH)
    if not chunks:
        raise RuntimeError(f"No text extracted from {BOOK_PATH}")

    rows: list[tuple[str, str, int, list[float]]] = []
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i : i + EMBED_BATCH_SIZE]
        embeddings = embed_texts([c.text for c in batch])
        rows.extend(
            (c.chunk_id, c.text, c.page, e) for c, e in zip(batch, embeddings, strict=True)
        )
        print(f"  embedded {min(i + EMBED_BATCH_SIZE, len(chunks))}/{len(chunks)} chunks", end="\r")

    with connection() as conn:
        BookChunkRepository(conn).replace_all(rows)

    pages = len({c.page for c in chunks})
    print(f"\nIndexed {len(rows)} chunks from {pages} pages into book_chunks")


if __name__ == "__main__":
    main()
