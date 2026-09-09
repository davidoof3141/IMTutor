from __future__ import annotations

import logging
import uuid
from typing import Literal

import pymupdf
from pydantic import BaseModel

from app.store.db import Conn

logger = logging.getLogger("app.attachments")

Kind = Literal["image", "document"]

# Content-type -> attachment kind. The learner's file picker is restricted to
# exactly these types (see ChatPanel's `accept`), this is the server-side gate.
ALLOWED_MIME: dict[str, Kind] = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "application/pdf": "document",
    "text/plain": "document",
    "text/markdown": "document",
}

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # documents
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # base64 inflates ~33%, and vision providers cap lower

# Extracted document text is fed into the prompt on every turn it's attached
# to, so it's capped well below the upload byte cap (PDF text can be much
# larger than the PDF itself).
MAX_EXTRACTED_CHARS = 40_000
_TRUNCATION_MARKER = "\n…[gekürzt]"

# A learner-uploaded PDF is parsed synchronously in the request, so a
# pathological file must not be able to tie a worker up. We stop well before
# the char cap would anyway (a 40k-char budget is ~15-20 pages of prose) and
# swallow any parser failure rather than 500 the upload.
_MAX_PDF_PAGES = 50


def extract_text(data: bytes, mime_type: str) -> str | None:
    """Best-effort text extraction for a document attachment, truncated to
    `MAX_EXTRACTED_CHARS`. Returns None for images, "" when extraction fails."""
    if mime_type == "application/pdf":
        text = _extract_pdf_text(data)
    elif mime_type in ("text/plain", "text/markdown"):
        text = data.decode("utf-8", errors="replace")
    else:
        return None
    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[: MAX_EXTRACTED_CHARS - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
    return text


def _extract_pdf_text(data: bytes) -> str:
    parts: list[str] = []
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for page in doc.pages(0, min(doc.page_count, _MAX_PDF_PAGES)):
                parts.append(page.get_text())
                if sum(len(p) for p in parts) >= MAX_EXTRACTED_CHARS:
                    break
    except Exception:
        logger.exception("PDF text extraction failed for a %d-byte upload", len(data))
        return ""
    return "\n\n".join(p for p in parts if p)


class AttachmentMeta(BaseModel):
    """Public shape: never carries the file bytes or extracted text."""

    id: str
    filename: str
    mime_type: str
    kind: Kind
    size_bytes: int


class AttachmentWithData(BaseModel):
    filename: str
    mime_type: str
    data: bytes


class AttachmentForChat(BaseModel):
    id: str
    filename: str
    mime_type: str
    kind: Kind
    extracted_text: str | None
    data: bytes


class AttachmentRepository:
    """Uploaded-file storage. Files live as bytes in Postgres -- this app has
    no object storage and deliberately avoids adding infra for it.

    An attachment starts unlinked (`conversation_id`/`message_id` NULL) since
    it's uploaded before the learner sends the turn it belongs to; `chat.py`
    links it to a conversation and then a specific message once the turn
    completes.
    """

    _META_COLUMNS = "id, filename, mime_type, kind, size_bytes"

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def create(
        self,
        *,
        learner_id: str,
        conversation_id: str | None,
        filename: str,
        mime_type: str,
        kind: Kind,
        size_bytes: int,
        data: bytes,
        extracted_text: str | None,
    ) -> AttachmentMeta:
        row = self._conn.execute(
            f"""
            INSERT INTO attachments
                (id, learner_id, conversation_id, filename, mime_type, kind,
                 size_bytes, data, extracted_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {self._META_COLUMNS}
            """,
            (
                str(uuid.uuid4()),
                learner_id,
                conversation_id,
                filename,
                mime_type,
                kind,
                size_bytes,
                data,
                extracted_text,
            ),
        ).fetchone()
        self._conn.commit()
        assert row is not None
        return AttachmentMeta(**row)

    def get_with_data(self, attachment_id: str, learner_id: str) -> AttachmentWithData | None:
        row = self._conn.execute(
            "SELECT filename, mime_type, data FROM attachments WHERE id = %s AND learner_id = %s",
            (attachment_id, learner_id),
        ).fetchone()
        return None if row is None else AttachmentWithData(**row)

    def resolve_for_chat(
        self, ids: list[str], learner_id: str, conversation_id: str
    ) -> list[AttachmentForChat]:
        """Assigns `conversation_id` to any of `ids` that don't have one yet,
        then returns the (owned, not-yet-linked-to-a-message) subset with
        their data -- silently dropping stale, foreign, or already-linked
        ids rather than failing the whole chat turn."""
        if not ids:
            return []
        rows = self._conn.execute(
            """
            UPDATE attachments
            SET conversation_id = COALESCE(conversation_id, %s)
            WHERE id = ANY(%s) AND learner_id = %s AND message_id IS NULL
                AND (conversation_id IS NULL OR conversation_id = %s)
            RETURNING id, filename, mime_type, kind, extracted_text, data
            """,
            (conversation_id, ids, learner_id, conversation_id),
        ).fetchall()
        self._conn.commit()
        by_id = {row["id"]: AttachmentForChat(**row) for row in rows}
        return [by_id[i] for i in ids if i in by_id]

    def link_to_message(self, ids: list[str], message_id: int) -> None:
        if not ids:
            return
        self._conn.execute(
            "UPDATE attachments SET message_id = %s WHERE id = ANY(%s)",
            (message_id, ids),
        )
        self._conn.commit()
