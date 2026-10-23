import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import Repos, get_repos, require_admin
from app.security import hash_password
from app.store.group_links import GroupLink
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


class CreateLinkUserRequest(BaseModel):
    # A blank/omitted username gets a random one -- the account is only ever
    # reached via its link, so the name just needs to be unique.
    username: str | None = Field(default=None, min_length=3, max_length=32)
    role: Role = "learner"


class LinkUserResponse(BaseModel):
    user: User
    # The raw, one-time-visible token. The frontend turns it into a full URL;
    # only its hash is ever persisted, so this is the caller's only chance to
    # see it.
    link_token: str


def _random_username() -> str:
    return f"learner-{secrets.token_hex(4)}"


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


@router.post("/link", response_model=LinkUserResponse, status_code=201)
def create_link_user(
    body: CreateLinkUserRequest,
    _: User = Depends(require_admin),
    repos: Repos = Depends(get_repos),
) -> LinkUserResponse:
    """Admin shortcut: create an already-approved account that has no usable
    password and is reached only through a generated login link."""
    username = body.username or _random_username()
    if repos.users.exists(username):
        raise HTTPException(status_code=409, detail="username already taken")
    user = repos.users.create(
        user_id=str(uuid.uuid4()),
        # The password is unknown to anyone -- a random value never surfaced,
        # kept only so the column's NOT NULL constraint is satisfied.
        username=username,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=body.role,
        status="approved",
    )
    token = repos.login_links.issue(user.id)
    return LinkUserResponse(user=user.model_copy(update={"has_login_link": True}), link_token=token)


class CreateGroupLinkRequest(BaseModel):
    label: str = Field(default="", max_length=80)
    max_uses: int = Field(default=30, ge=1, le=500)
    expires_in_days: int = Field(default=14, ge=1, le=90)


class GroupLinkCreated(BaseModel):
    link: GroupLink
    # Raw token, visible only in this response.
    token: str


@router.post("/group-links", response_model=GroupLinkCreated, status_code=201)
def create_group_link(
    body: CreateGroupLinkRequest,
    _: User = Depends(require_admin),
    repos: Repos = Depends(get_repos),
) -> GroupLinkCreated:
    """A shared sign-up link: each visitor gets their own link-invited
    account, up to `max_uses` of them before `expires_in_days` run out."""
    link, token = repos.group_links.create(
        label=body.label.strip(), max_uses=body.max_uses, expires_in_days=body.expires_in_days
    )
    return GroupLinkCreated(link=link, token=token)


@router.get("/group-links", response_model=list[GroupLink])
def list_group_links(
    _: User = Depends(require_admin), repos: Repos = Depends(get_repos)
) -> list[GroupLink]:
    return repos.group_links.list_all()


@router.post("/group-links/{link_id}/revoke", status_code=204)
def revoke_group_link(
    link_id: str, _: User = Depends(require_admin), repos: Repos = Depends(get_repos)
) -> None:
    """Stops the link creating new accounts; accounts it already made keep working."""
    if not repos.group_links.revoke(link_id):
        raise HTTPException(status_code=404, detail="group link not found")


@router.post("/{user_id}/link", response_model=LinkUserResponse)
def regenerate_link(
    user_id: str,
    _: User = Depends(require_admin),
    repos: Repos = Depends(get_repos),
) -> LinkUserResponse:
    """(Re)issue a login link for an existing user -- replaces any link it
    already had, so a leaked or lost link can be invalidated by generating a
    fresh one."""
    user = repos.users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    token = repos.login_links.issue(user_id)
    return LinkUserResponse(user=user.model_copy(update={"has_login_link": True}), link_token=token)


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
