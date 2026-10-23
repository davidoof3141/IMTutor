import secrets
import uuid
from typing import Any

from pydantic import BaseModel

from app.store.db import Conn
from app.store.login_links import _hash


class GroupLink(BaseModel):
    id: str
    label: str
    max_uses: int
    uses: int
    expires_at: str
    revoked: bool
    created_at: str


class GroupLinkRepository:
    """Shared sign-up links for study groups. One raw token (only its hash is
    stored) lets up to `max_uses` people each get their own link-invited
    account, until it expires or an admin revokes it -- the cap is what bounds
    the cost of a leaked link."""

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def create(self, *, label: str, max_uses: int, expires_in_days: int) -> tuple[GroupLink, str]:
        """Returns the new link and its raw token (shown to the caller once)."""
        token = secrets.token_urlsafe(32)
        row = self._conn.execute(
            """
            INSERT INTO group_links (id, token_hash, label, max_uses, expires_at)
            VALUES (%s, %s, %s, %s, now() + make_interval(days => %s))
            RETURNING id, label, max_uses, uses, expires_at, revoked, created_at
            """,
            (str(uuid.uuid4()), _hash(token), label, max_uses, expires_in_days),
        ).fetchone()
        self._conn.commit()
        assert row is not None
        return _to_model(row), token

    def claim(self, token: str) -> str | None:
        """Atomically uses up one slot. Returns the link id, or None if the
        token is unknown, revoked, expired or already fully used."""
        row = self._conn.execute(
            """
            UPDATE group_links SET uses = uses + 1
            WHERE token_hash = %s AND NOT revoked AND uses < max_uses AND expires_at > now()
            RETURNING id
            """,
            (_hash(token),),
        ).fetchone()
        self._conn.commit()
        return None if row is None else str(row["id"])

    def attach_user(self, user_id: str, group_link_id: str) -> None:
        self._conn.execute(
            "UPDATE users SET group_link_id = %s WHERE id = %s", (group_link_id, user_id)
        )
        self._conn.commit()

    def list_all(self) -> list[GroupLink]:
        rows = self._conn.execute(
            """
            SELECT id, label, max_uses, uses, expires_at, revoked, created_at
            FROM group_links ORDER BY created_at DESC
            """
        ).fetchall()
        return [_to_model(r) for r in rows]

    def revoke(self, link_id: str) -> bool:
        row = self._conn.execute(
            "UPDATE group_links SET revoked = TRUE WHERE id = %s RETURNING id", (link_id,)
        ).fetchone()
        self._conn.commit()
        return row is not None


def _to_model(row: Any) -> GroupLink:
    return GroupLink(
        id=str(row["id"]),
        label=row["label"],
        max_uses=row["max_uses"],
        uses=row["uses"],
        expires_at=row["expires_at"].isoformat(),
        revoked=row["revoked"],
        created_at=row["created_at"].isoformat(),
    )
