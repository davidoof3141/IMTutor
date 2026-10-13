"""A chapter's text as stored in Postgres, and its content hash.

The book's chapters are not rows of their own: the chapter list comes from the
PDF outline (rag/toc.py), and `book_chunks` holds page-tagged chunks. A
chapter's text is therefore the chunks on its page range, in page / chunk
order, concatenated. The hash of that text is what a generated diagnostic
records as `source_hash`, so a rebuilt book index shows up as drift.
"""

import hashlib
import re

from app.rag.toc import Chapter
from app.store.db import Conn

_CHUNK_INDEX = re.compile(r"-(\d+)$")
CHUNK_SEPARATOR = "\n"


def chapter_text(conn: Conn, chapter: Chapter) -> str:
    rows = conn.execute(
        "SELECT chunk_id, text, page FROM book_chunks WHERE page BETWEEN %s AND %s",
        (chapter.page_start, chapter.page_end),
    ).fetchall()

    def order(row: dict) -> tuple[int, int]:  # type: ignore[type-arg]
        match = _CHUNK_INDEX.search(row["chunk_id"])
        return row["page"], int(match.group(1)) if match else 0

    return CHUNK_SEPARATOR.join(row["text"] for row in sorted(rows, key=order))


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current_hashes(conn: Conn, curriculum: list[Chapter]) -> dict[str, str]:
    """chapter number -> hash of its current text, for chapters that have any."""
    hashes: dict[str, str] = {}
    for chapter in curriculum:
        text = chapter_text(conn, chapter)
        if text:
            hashes[chapter.number] = source_hash(text)
    return hashes
