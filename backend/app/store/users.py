from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.store.db import Conn

Role = Literal["admin", "learner"]
Status = Literal["pending", "approved", "rejected"]


class User(BaseModel):
    """A user account. The password hash is never part of this model."""

    id: str
    username: str
    role: Role
    status: Status
    created_at: datetime


class UserRepository:
    """Account storage and the registration/approval lifecycle.

    Kept out of app/core -- authentication is not part of the deterministic
    control layer and core/ must not depend on it.
    """

    _COLUMNS = "id, username, role, status, created_at"

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def exists(self, username: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM users WHERE username = %s", (username,)
        ).fetchone()
        return row is not None

    def create(
        self, *, user_id: str, username: str, password_hash: str, role: Role, status: Status
    ) -> User:
        row = self._conn.execute(
            f"""
            INSERT INTO users (id, username, password_hash, role, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING {self._COLUMNS}
            """,
            (user_id, username, password_hash, role, status),
        ).fetchone()
        self._conn.commit()
        assert row is not None
        return User(**row)

    def get(self, user_id: str) -> User | None:
        row = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        return None if row is None else User(**row)

    def get_by_username_with_hash(self, username: str) -> tuple[User, str] | None:
        row = self._conn.execute(
            f"SELECT {self._COLUMNS}, password_hash FROM users WHERE username = %s",
            (username,),
        ).fetchone()
        if row is None:
            return None
        password_hash = row.pop("password_hash")
        return User(**row), password_hash

    def list_all(self) -> list[User]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM users ORDER BY created_at ASC"
        ).fetchall()
        return [User(**row) for row in rows]

    def set_status(self, user_id: str, status: Status) -> User | None:
        row = self._conn.execute(
            f"UPDATE users SET status = %s WHERE id = %s RETURNING {self._COLUMNS}",
            (status, user_id),
        ).fetchone()
        self._conn.commit()
        return None if row is None else User(**row)

    def set_role(self, user_id: str, role: Role) -> User | None:
        row = self._conn.execute(
            f"UPDATE users SET role = %s WHERE id = %s RETURNING {self._COLUMNS}",
            (role, user_id),
        ).fetchone()
        self._conn.commit()
        return None if row is None else User(**row)
