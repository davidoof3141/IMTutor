import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import (
    Repos,
    get_current_user_allow_pw_change,
    get_repos,
)
from app.security import create_token, hash_password, verify_password
from app.store.users import User, UsernameTaken

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Fixed-window abuse caps, per client, for the two unauthenticated endpoints.
# Generous enough that a fat-fingered human never notices; tight enough that
# online password guessing and bulk-registration are not practical.
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 5 * 60
_REGISTER_MAX_ATTEMPTS = 10
_REGISTER_WINDOW_SECONDS = 60 * 60


def _client_id(request: Request) -> str:
    """Best-effort caller identity for rate limiting. Trusts the first
    `X-Forwarded-For` hop (set by the platform proxy in front of the app);
    falls back to the socket peer for a direct connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request, repos: Repos, action: str, limit: int, window: int) -> None:
    if repos.rate_limits.hit(f"{action}:{_client_id(request)}", limit=limit, window_seconds=window):
        raise HTTPException(
            status_code=429,
            detail="too many attempts, please wait a few minutes and try again",
        )


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    status: str


class LoginResponse(BaseModel):
    token: str
    user: User


class MeResponse(BaseModel):
    user: User
    learner_id: str | None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(
    body: Credentials, request: Request, repos: Repos = Depends(get_repos)
) -> RegisterResponse:
    _rate_limit(
        request, repos, "register", _REGISTER_MAX_ATTEMPTS, _REGISTER_WINDOW_SECONDS
    )
    try:
        repos.users.create(
            user_id=str(uuid.uuid4()),
            username=body.username,
            password_hash=hash_password(body.password),
            role="learner",
            status="pending",
        )
    except UsernameTaken:
        # Deliberately not surfaced: a distinct "already taken" response lets
        # an attacker enumerate registered usernames. The caller sees the
        # same "pending" either way.
        pass
    return RegisterResponse(status="pending")


@router.post("/login", response_model=LoginResponse)
def login(
    body: Credentials, request: Request, repos: Repos = Depends(get_repos)
) -> LoginResponse:
    _rate_limit(request, repos, "login", _LOGIN_MAX_ATTEMPTS, _LOGIN_WINDOW_SECONDS)
    found = repos.users.get_by_username_with_hash(body.username)
    if found is None or not verify_password(body.password, found[1]):
        raise HTTPException(status_code=401, detail="wrong username or password")
    user, _ = found
    if user.status == "pending":
        raise HTTPException(status_code=403, detail="account is awaiting admin approval")
    if user.status == "rejected":
        raise HTTPException(status_code=403, detail="account was rejected by an admin")
    return LoginResponse(token=create_token(user.id, user.token_version), user=user)


@router.get("/me", response_model=MeResponse)
def me(
    user: User = Depends(get_current_user_allow_pw_change),
    repos: Repos = Depends(get_repos),
) -> MeResponse:
    return MeResponse(user=user, learner_id=repos.profiles.get_learner_id_for_user(user.id))


@router.post("/change-password", response_model=LoginResponse)
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user_allow_pw_change),
    repos: Repos = Depends(get_repos),
) -> LoginResponse:
    """Set a new password for the signed-in account. Also the exit door from a
    forced one-time-password change -- it is the one authenticated endpoint
    such an account may call."""
    found = repos.users.get_by_username_with_hash(user.username)
    if found is None or not verify_password(body.current_password, found[1]):
        raise HTTPException(status_code=401, detail="current password is wrong")
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=400, detail="new password must differ from the current one"
        )
    updated = repos.users.set_password(user.id, hash_password(body.new_password))
    assert updated is not None  # the row was just read above
    return LoginResponse(
        token=create_token(updated.id, updated.token_version), user=updated
    )
