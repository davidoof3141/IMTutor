from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from app.core.clauses import ClauseCatalogue
from app.core.diagnostic import Diagnostic, ScoringTable, resolve_diagnostic
from app.core.mapping import derive, effective
from app.core.planner import PlannerTable
from app.core.profile import Profile
from app.core.rules import RuleSet
from app.core.step_templates import StepTemplates
from app.core.vector import Attribution, ControlVector, Override
from app.rag.toc import Chapter
from app.security import decode_token
from app.store.attachments import AttachmentRepository
from app.store.chapter_diagnostics import ChapterDiagnosticRepository, StoredDiagnostic
from app.store.comparisons import ComparisonRepository
from app.store.conversations import ConversationRepository
from app.store.db import connection, ensure_schema
from app.store.lessons import LessonRepository
from app.store.group_links import GroupLinkRepository
from app.store.login_links import LoginLinkRepository
from app.store.override_changes import OverrideChangeRepository
from app.store.overrides import OverrideRepository
from app.store.profiles import ProfileRepository
from app.store.rate_limit import RateLimitRepository
from app.store.sessions import SessionRepository
from app.store.study_mode import StudyModeRepository, StudyModeState
from app.store.turn_logs import TurnLogRepository
from app.store.users import User, UserRepository


@dataclass
class AppState:
    rulesets: dict[str, RuleSet]
    catalogues: dict[str, ClauseCatalogue]
    curriculum: list[Chapter]
    planner_tables: dict[str, PlannerTable]
    step_templates: dict[str, StepTemplates]
    # chapter number -> reviewed, committed diagnostic (backend/content/diagnostics/); may be empty
    diagnostics: dict[str, Diagnostic]
    scoring_table: ScoringTable


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.itm
    return state


@dataclass
class Repos:
    profiles: ProfileRepository
    overrides: OverrideRepository
    override_changes: OverrideChangeRepository
    sessions: SessionRepository
    study_mode: StudyModeRepository
    turn_logs: TurnLogRepository
    users: UserRepository
    login_links: LoginLinkRepository
    group_links: GroupLinkRepository
    conversations: ConversationRepository
    comparisons: ComparisonRepository
    attachments: AttachmentRepository
    lessons: LessonRepository
    rate_limits: RateLimitRepository
    chapter_diagnostics: ChapterDiagnosticRepository


def get_repos() -> Iterator[Repos]:
    """Borrows one pooled Postgres connection for the duration of the request."""
    ensure_schema()  # no-op after the first request that reaches the database
    with connection() as conn:
        yield Repos(
            profiles=ProfileRepository(conn),
            overrides=OverrideRepository(conn),
            override_changes=OverrideChangeRepository(conn),
            sessions=SessionRepository(conn),
            study_mode=StudyModeRepository(conn),
            turn_logs=TurnLogRepository(conn),
            users=UserRepository(conn),
            login_links=LoginLinkRepository(conn),
            group_links=GroupLinkRepository(conn),
            conversations=ConversationRepository(conn),
            comparisons=ComparisonRepository(conn),
            attachments=AttachmentRepository(conn),
            lessons=LessonRepository(conn),
            rate_limits=RateLimitRepository(conn),
            chapter_diagnostics=ChapterDiagnosticRepository(conn),
        )


def get_current_user_allow_pw_change(
    request: Request, repos: Repos = Depends(get_repos)
) -> User:
    """The authenticated, approved user behind an `Authorization: Bearer`
    header -- but without the "must not owe a password change" gate.

    Only `/api/auth/me` and `/api/auth/change-password` use this: a freshly
    created account holding a one-time password needs to reach both before it
    has cleared the flag. Every other route depends on `get_current_user`.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    claims = decode_token(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    user = repos.users.get(claims.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="account no longer exists")
    if claims.token_version != user.token_version:
        raise HTTPException(status_code=401, detail="token has been revoked")
    if user.status != "approved":
        raise HTTPException(status_code=403, detail=f"account {user.status}")
    return user


def get_current_user(
    user: User = Depends(get_current_user_allow_pw_change),
) -> User:
    """The authenticated, approved user, additionally barred while the account
    still owes a forced password change."""
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="password change required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user


@dataclass(frozen=True)
class ResolvedConfig:
    derived: ControlVector
    attribution: Attribution
    override: Override
    effective: ControlVector
    # The completed chapter diagnostic this config was derived with, if any.
    diagnostic: StoredDiagnostic | None


def completed_diagnostic(
    profile: Profile, state: AppState, repos: Repos, study_mode: StudyModeState
) -> StoredDiagnostic | None:
    """The learner's stored result for the diagnostic covering their current
    training selection (None: no selection, no diagnostic authored, or not
    taken yet)."""
    if study_mode.mode != "training" or study_mode.chapter_number is None:
        return None
    diagnostic = resolve_diagnostic(state.diagnostics, study_mode.chapter_number)
    if diagnostic is None:
        return None
    return repos.chapter_diagnostics.get(profile.learner_id, diagnostic.chapter_id)


def resolve_config(profile: Profile, state: AppState, repos: Repos) -> ResolvedConfig:
    """derived + overrides for the learner's current selection -- shared by
    every route that assembles a system prompt or compares against a lesson
    plan's frozen `vector_snapshot`.

    With a completed chapter diagnostic the chapter-level prior knowledge
    replaces the seed for the mapping call; the learner's global overrides are
    applied next, then the per-chapter overrides from the summary screen."""
    study_mode = repos.study_mode.get(profile.learner_id)
    stored = completed_diagnostic(profile, state, repos, study_mode)
    ruleset = state.rulesets[profile.ruleset_version]
    derived, attribution = derive(
        profile, ruleset, stored.prior_knowledge if stored is not None else None
    )
    override = repos.overrides.get(profile.learner_id)
    if stored is not None:
        override = {**override, **stored.override}
    return ResolvedConfig(
        derived=derived,
        attribution=attribution,
        override=override,
        effective=effective(derived, override),
        diagnostic=stored,
    )


def current_vector(profile: Profile, state: AppState, repos: Repos) -> ControlVector:
    return resolve_config(profile, state, repos).effective


def require_diagnostic_done(profile: Profile, state: AppState, repos: Repos) -> None:
    """409 while the current training selection has an authored diagnostic the
    learner has not taken yet: it must run BEFORE the first instructional turn."""
    study_mode = repos.study_mode.get(profile.learner_id)
    if study_mode.mode != "training" or study_mode.chapter_number is None:
        return
    diagnostic = resolve_diagnostic(state.diagnostics, study_mode.chapter_number)
    if diagnostic is None:
        return
    if repos.chapter_diagnostics.get(profile.learner_id, diagnostic.chapter_id) is None:
        raise HTTPException(status_code=409, detail="diagnostic_required")


def authorize_learner(learner_id: str, user: User, repos: Repos) -> None:
    """404 if the learner profile is unknown, 403 if it isn't the caller's.

    Admins may act on any learner. A profile with no owner (`user_id is
    None` -- only pre-auth legacy rows) belongs to nobody and is reachable
    by admins only.
    """
    profile = repos.profiles.get(learner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="learner not found")
    if user.role == "admin":
        return
    if profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="not your learner profile")
