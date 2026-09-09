from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from app.core.clauses import ClauseCatalogue
from app.core.mapping import derive, effective
from app.core.planner import PlannerTable
from app.core.profile import Profile
from app.core.rules import RuleSet
from app.core.step_templates import StepTemplates
from app.core.vector import ControlVector
from app.rag.toc import Chapter
from app.security import decode_token
from app.store.attachments import AttachmentRepository
from app.store.conversations import ConversationRepository
from app.store.db import connection
from app.store.lessons import LessonRepository
from app.store.overrides import OverrideRepository
from app.store.profiles import ProfileRepository
from app.store.sessions import SessionRepository
from app.store.study_mode import StudyModeRepository
from app.store.turn_logs import TurnLogRepository
from app.store.users import User, UserRepository


@dataclass
class AppState:
    rulesets: dict[str, RuleSet]
    catalogues: dict[str, ClauseCatalogue]
    curriculum: list[Chapter]
    planner_tables: dict[str, PlannerTable]
    step_templates: dict[str, StepTemplates]


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.itm
    return state


@dataclass
class Repos:
    profiles: ProfileRepository
    overrides: OverrideRepository
    sessions: SessionRepository
    study_mode: StudyModeRepository
    turn_logs: TurnLogRepository
    users: UserRepository
    conversations: ConversationRepository
    attachments: AttachmentRepository
    lessons: LessonRepository


def get_repos() -> Iterator[Repos]:
    """Borrows one pooled Postgres connection for the duration of the request."""
    with connection() as conn:
        yield Repos(
            profiles=ProfileRepository(conn),
            overrides=OverrideRepository(conn),
            sessions=SessionRepository(conn),
            study_mode=StudyModeRepository(conn),
            turn_logs=TurnLogRepository(conn),
            users=UserRepository(conn),
            conversations=ConversationRepository(conn),
            attachments=AttachmentRepository(conn),
            lessons=LessonRepository(conn),
        )


def get_current_user(request: Request, repos: Repos = Depends(get_repos)) -> User:
    """The authenticated, approved user behind an `Authorization: Bearer` header."""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    user_id = decode_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    user = repos.users.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="account no longer exists")
    if user.status != "approved":
        raise HTTPException(status_code=403, detail=f"account {user.status}")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user


def current_vector(profile: Profile, state: AppState, repos: Repos) -> ControlVector:
    """The learner's current effective vector (derived + overrides) --
    shared by every route that needs to assemble a system prompt or compare
    against a lesson plan's frozen `vector_snapshot`."""
    ruleset = state.rulesets[profile.ruleset_version]
    derived, _ = derive(profile, ruleset)
    override = repos.overrides.get(profile.learner_id)
    return effective(derived, override)


def authorize_learner(learner_id: str, user: User, repos: Repos) -> None:
    """404 if the learner profile is unknown, 403 if it isn't the caller's.

    Admins may act on any learner. Legacy profiles without an owner
    (`user_id is None`) are readable by any authenticated user.
    """
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")
    if user.role == "admin":
        return
    if profile.user_id is not None and profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="not your learner profile")
