"""Password hashing and bearer-token issuing.

Deliberately outside app/core: authentication is not part of the deterministic
control layer, and core/ must stay free of framework and I/O concerns.
"""

import os
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

_ALGORITHM = "HS256"
_TOKEN_TTL = timedelta(days=7)
_DEV_SECRET = "dev-secret-change-me-not-for-any-real-deployment"


def _secret() -> str:
    return os.environ.get("AUTH_SECRET", _DEV_SECRET)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + _TOKEN_TTL}
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> str | None:
    """Return the user id from a valid token, or None if it is invalid/expired."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
