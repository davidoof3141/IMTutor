"""Rebuilds the local vector index over the course textbook.

Run after the book PDF changes, or once before the first chat request:

    uv run python scripts/build_book_index.py
"""

import shutil

from app.rag.chunking import BOOK_PATH, chunk_book
from app.rag.index import DEFAULT_INDEX_DIR, get_collection

BATCH_SIZE = 256


def main() -> None:
    if DEFAULT_INDEX_DIR.exists():
        shutil.rmtree(DEFAULT_INDEX_DIR)

    chunks = chunk_book(BOOK_PATH)
    if not chunks:
        raise RuntimeError(f"No text extracted from {BOOK_PATH}")

    collection = get_collection(DEFAULT_INDEX_DIR)
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        collection.add(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[{"page": c.page} for c in batch],
        )
        print(f"  indexed {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)} chunks", end="\r")

    pages = len({c.page for c in chunks})
    print(f"\nIndexed {len(chunks)} chunks from {pages} pages into {DEFAULT_INDEX_DIR}")


if __name__ == "__main__":
    main()
