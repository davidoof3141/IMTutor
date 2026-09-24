import hashlib
import secrets

from app.store.db import Conn


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginLinkRepository:
    """Passwordless "magic link" login: a random token whose hash is stored
    (same treatment as a password) and swapped out wholesale on re-issue, so
    an account has at most one working link at a time.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def issue(self, user_id: str) -> str:
        """Create this user's login link, replacing any previous one, and
        return the raw token. The token is shown to the caller exactly once --
        only its hash is ever persisted."""
        token = secrets.token_urlsafe(32)
        self._conn.execute(
            """
            INSERT INTO login_links (user_id, token_hash)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET token_hash = EXCLUDED.token_hash, created_at = now()
            """,
            (user_id, _hash(token)),
        )
        self._conn.commit()
        return token

    def resolve(self, token: str) -> str | None:
        """The user id owning this token, or None if it is unknown."""
        row = self._conn.execute(
            "SELECT user_id FROM login_links WHERE token_hash = %s", (_hash(token),)
        ).fetchone()
        return None if row is None else str(row["user_id"])
