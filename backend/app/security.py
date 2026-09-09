"""Password hashing and bearer-token issuing.

Deliberately outside app/core: authentication is not part of the deterministic
control layer, and core/ must stay free of framework and I/O concerns.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

_ALGORITHM = "HS256"
_TOKEN_TTL = timedelta(days=7)
_DEV_SECRET = "dev-secret-change-me-not-for-any-real-deployment"


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    token_version: int


def _secret() -> str:
    return os.environ.get("AUTH_SECRET", _DEV_SECRET)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user_id: str, token_version: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "ver": token_version,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> TokenClaims | None:
    """Return the claims from a valid token, or None if it is invalid/expired.

    A token missing `ver` (issued before token versioning existed) is treated
    as version 0, which matches the column default for pre-migration rows.
    """
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    sub = payload.get("sub")
    if not isinstance(sub, str):
        return None
    ver = payload.get("ver", 0)
    return TokenClaims(user_id=sub, token_version=ver if isinstance(ver, int) else 0)
