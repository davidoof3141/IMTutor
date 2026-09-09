from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.store.attachments import AttachmentMeta
from app.store.db import Conn
from app.store.study_mode import StudyModeState

Role = Literal["learner", "tutor"]

# The tutor is fed at most this many prior messages when resuming a conversation,
# so a long thread can't blow past the model's context window (or the bill).
MAX_HISTORY_MESSAGES = 20

# A conversation's title is the first learner message, trimmed to this length.
_TITLE_MAX_CHARS = 80


class BookImageRef(BaseModel):
    id: str
    page: int


class Message(BaseModel):
    role: Role
    text: str
    created_at: datetime
    attachments: list[AttachmentMeta] = []
    book_images: list[BookImageRef] = []
    page_refs: list[int] = []


class Conversation(BaseModel):
    id: str
    learner_id: str
    title: str | None = None
    mode: str | None = None
    chapter_number: str | None = None
    section_number: str | None = None
    created_at: datetime
    last_message_at: datetime
    message_count: int = 0


class ConversationRepository:
    """Stored chat threads: one row per conversation, one row per message.

    Separate from the turn-log JSONL (that stays the append-only evaluation
    dataset). This is the learner-facing history -- what the sidebar lists and
    what gets replayed to the model when a thread is resumed.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def create(self, learner_id: str, study_mode: StudyModeState | None = None) -> Conversation:
        conversation_id = str(uuid.uuid4())
        mode = study_mode.mode if study_mode else None
        chapter = study_mode.chapter_number if study_mode else None
        section = study_mode.section_number if study_mode else None
        row = self._conn.execute(
            """
            INSERT INTO conversations (id, learner_id, mode, chapter_number, section_number)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, learner_id, title, mode, chapter_number, section_number,
                      created_at, last_message_at
            """,
            (conversation_id, learner_id, mode, chapter, section),
        ).fetchone()
        self._conn.commit()
        assert row is not None
        return Conversation(**row, message_count=0)

    def get(self, conversation_id: str) -> Conversation | None:
        row = self._conn.execute(
            """
            SELECT c.id, c.learner_id, c.title, c.mode, c.chapter_number, c.section_number,
                   c.created_at, c.last_message_at,
                   (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            WHERE c.id = %s
            """,
            (conversation_id,),
        ).fetchone()
        return Conversation(**row) if row is not None else None

    def for_learner(self, learner_id: str) -> list[Conversation]:
        rows = self._conn.execute(
            """
            SELECT c.id, c.learner_id, c.title, c.mode, c.chapter_number, c.section_number,
                   c.created_at, c.last_message_at,
                   (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            WHERE c.learner_id = %s
            ORDER BY c.last_message_at DESC
            """,
            (learner_id,),
        ).fetchall()
        return [Conversation(**row) for row in rows]

    # Two correlated subqueries rather than joins -- attachments and book
    # images are both one-to-many off messages, and joining both at once
    # would cross-product them under a single GROUP BY.
    _MESSAGE_COLUMNS = """
        m.role, m.text, m.created_at,
        COALESCE(
            (SELECT json_agg(json_build_object(
                'id', a.id, 'filename', a.filename, 'mime_type', a.mime_type,
                'kind', a.kind, 'size_bytes', a.size_bytes
            ) ORDER BY a.created_at)
             FROM attachments a WHERE a.message_id = m.id),
            '[]'::json
        ) AS attachments,
        COALESCE(
            (SELECT json_agg(json_build_object('id', bi.image_id, 'page', bi.page) ORDER BY bi.page)
             FROM message_book_images bi WHERE bi.message_id = m.id),
            '[]'::json
        ) AS book_images,
        COALESCE(
            (SELECT json_agg(pr.page ORDER BY pr.page)
             FROM message_page_refs pr WHERE pr.message_id = m.id),
            '[]'::json
        ) AS page_refs
    """

    def messages(self, conversation_id: str, limit: int | None = None) -> list[Message]:
        """Messages oldest-first. With `limit`, the most recent `limit` of them."""
        if limit is None:
            rows = self._conn.execute(
                f"SELECT {self._MESSAGE_COLUMNS} FROM messages m "
                "WHERE m.conversation_id = %s ORDER BY m.id",
                (conversation_id,),
            ).fetchall()
            return [Message(**row) for row in rows]
        rows = self._conn.execute(
            f"SELECT {self._MESSAGE_COLUMNS} FROM messages m "
            "WHERE m.conversation_id = %s ORDER BY m.id DESC LIMIT %s",
            (conversation_id, limit),
        ).fetchall()
        return [Message(**row) for row in reversed(rows)]

    def add_turn(
        self,
        conversation_id: str,
        learner_text: str,
        tutor_text: str,
        book_image_refs: list[tuple[str, int]] | None = None,
        page_refs: list[int] | None = None,
    ) -> int:
        """Append one learner message and the tutor's reply (tagged with the
        book images and source pages retrieval surfaced, if any), bump the
        conversation's `last_message_at` (setting its title on the first
        turn), and return the learner message's id -- so attachments passed
        in on this turn can be linked to it."""
        learner_row = self._conn.execute(
            "INSERT INTO messages (conversation_id, role, text) VALUES (%s, 'learner', %s) "
            "RETURNING id",
            (conversation_id, learner_text),
        ).fetchone()
        tutor_row = self._conn.execute(
            "INSERT INTO messages (conversation_id, role, text) VALUES (%s, 'tutor', %s) "
            "RETURNING id",
            (conversation_id, tutor_text),
        ).fetchone()
        assert tutor_row is not None
        for image_id, page in book_image_refs or []:
            self._conn.execute(
                "INSERT INTO message_book_images (message_id, image_id, page) VALUES (%s, %s, %s)",
                (tutor_row["id"], image_id, page),
            )
        for page in page_refs or []:
            self._conn.execute(
                "INSERT INTO message_page_refs (message_id, page) VALUES (%s, %s)",
                (tutor_row["id"], page),
            )
        self._conn.execute(
            """
            UPDATE conversations
            SET last_message_at = now(),
                title = COALESCE(title, %s)
            WHERE id = %s
            """,
            (_title_from(learner_text), conversation_id),
        )
        self._conn.commit()
        assert learner_row is not None
        return int(learner_row["id"])

    def add_tutor_message(self, conversation_id: str, text: str) -> int:
        """Appends a tutor message with no paired learner message -- for a
        server-initiated lesson-step turn, where nothing was actually typed.
        Bumps `last_message_at` like add_turn; never sets the title (a
        lesson-step message is never the learner's first turn in a fresh
        thread -- see app/api/lesson.py, which creates the conversation and
        the plan together)."""
        tutor_row = self._conn.execute(
            "INSERT INTO messages (conversation_id, role, text) VALUES (%s, 'tutor', %s) "
            "RETURNING id",
            (conversation_id, text),
        ).fetchone()
        self._conn.execute(
            "UPDATE conversations SET last_message_at = now() WHERE id = %s",
            (conversation_id,),
        )
        self._conn.commit()
        assert tutor_row is not None
        return int(tutor_row["id"])


def _title_from(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _TITLE_MAX_CHARS:
        return collapsed
    return collapsed[: _TITLE_MAX_CHARS - 1].rstrip() + "…"
