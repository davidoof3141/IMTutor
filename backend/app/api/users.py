import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import Repos, get_repos, require_admin
from app.security import hash_password
from app.store.users import Role, Status, User

router = APIRouter(prefix="/api/users", tags=["users"])


class StatusRequest(BaseModel):
    status: Status


class RoleRequest(BaseModel):
    role: Role


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    role: Role = "admin"
    # When true the password is one-time: the account must set a new one
    # immediately after its first login.
    temporary_password: bool = False


@router.get("", response_model=list[User])
def list_users(
    _: User = Depends(require_admin), repos: Repos = Depends(get_repos)
) -> list[User]:
    return repos.users.list_all()


@router.post("", response_model=User, status_code=201)
def create_user(
    body: CreateUserRequest,
    _: User = Depends(require_admin),
    repos: Repos = Depends(get_repos),
) -> User:
    """Admin-only shortcut to create an already-approved account directly,
    skipping the register → approve flow. Used mainly to add fellow admins."""
    if repos.users.exists(body.username):
        raise HTTPException(status_code=409, detail="username already taken")
    return repos.users.create(
        user_id=str(uuid.uuid4()),
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        status="approved",
        must_change_password=body.temporary_password,
    )


@router.post("/{user_id}/status", response_model=User)
def set_status(
    user_id: str,
    body: StatusRequest,
    admin: User = Depends(require_admin),
    repos: Repos = Depends(get_repos),
) -> User:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="cannot change your own status")
    updated = repos.users.set_status(user_id, body.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="user not found")
    return updated


@router.post("/{user_id}/role", response_model=User)
def set_role(
    user_id: str,
    body: RoleRequest,
    admin: User = Depends(require_admin),
    repos: Repos = Depends(get_repos),
) -> User:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="cannot change your own role")
    updated = repos.users.set_role(user_id, body.role)
    if updated is None:
        raise HTTPException(status_code=404, detail="user not found")
    return updated
