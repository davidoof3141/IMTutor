import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import Repos, get_current_user, get_repos
from app.security import create_token, hash_password, verify_password
from app.store.users import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


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


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(body: Credentials, repos: Repos = Depends(get_repos)) -> RegisterResponse:
    if repos.users.exists(body.username):
        raise HTTPException(status_code=409, detail="username already taken")
    repos.users.create(
        user_id=str(uuid.uuid4()),
        username=body.username,
        password_hash=hash_password(body.password),
        role="learner",
        status="pending",
    )
    return RegisterResponse(status="pending")


@router.post("/login", response_model=LoginResponse)
def login(body: Credentials, repos: Repos = Depends(get_repos)) -> LoginResponse:
    found = repos.users.get_by_username_with_hash(body.username)
    if found is None or not verify_password(body.password, found[1]):
        raise HTTPException(status_code=401, detail="wrong username or password")
    user, _ = found
    if user.status == "pending":
        raise HTTPException(status_code=403, detail="account is awaiting admin approval")
    if user.status == "rejected":
        raise HTTPException(status_code=403, detail="account was rejected by an admin")
    return LoginResponse(token=create_token(user.id), user=user)


@router.get("/me", response_model=MeResponse)
def me(
    user: User = Depends(get_current_user), repos: Repos = Depends(get_repos)
) -> MeResponse:
    return MeResponse(user=user, learner_id=repos.profiles.get_learner_id_for_user(user.id))
