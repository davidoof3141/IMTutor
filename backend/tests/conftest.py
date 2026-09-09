import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.clauses import ClauseCatalogue, load_catalogue
from app.core.planner import PlannerTable, load_planner_table
from app.core.profile import Goal, LearnerType, PriorExperience, Profile, Role, StudyTime
from app.core.rules import RuleSet, load_ruleset
from app.core.step_templates import StepTemplates, load_step_templates
from app.rag.chunking import BOOK_PATH
from app.rag.toc import Chapter, extract_curriculum
from app.store.db import Conn

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"

_TABLES = (
    "users, profiles, overrides, study_mode, sessions, conversations, messages, attachments, "
    "lesson_plans, lesson_steps, turn_logs, book_chunks, rate_limits"
)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A throwaway Postgres for the DB-touching tests.

    Prefers a Docker container (testcontainers); falls back to an embedded
    server (pgserver) so the suite also runs where Docker is unavailable.
    Skips only if neither is possible.
    """
    for start in (_start_testcontainer, _start_pgserver):
        result = start()
        if result is not None:
            url, stop = result
            os.environ["DATABASE_URL"] = url
            os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-plenty-long-for-hs256")
            os.environ.setdefault("SUPERUSER_USERNAME", "root")
            os.environ.setdefault("SUPERUSER_PASSWORD", "rootpassword")
            try:
                yield url
            finally:
                stop()
            return
    pytest.skip("no Postgres available (need Docker or the pgserver package)")


def _start_testcontainer() -> "tuple[str, object] | None":
    try:
        try:
            from testcontainers.community.postgres import PostgresContainer
        except ImportError:
            from testcontainers.postgres import PostgresContainer
        container = PostgresContainer("postgres:16-alpine", driver=None)
        container.start()
    except Exception:  # noqa: BLE001 - any failure means "no Docker here"
        return None
    return container.get_connection_url(), container.stop


def _start_pgserver() -> "tuple[str, object] | None":
    try:
        import pgserver
        import psycopg
    except ImportError:
        return None
    server = pgserver.get_server(tempfile.mkdtemp(prefix="itm-pg-"))
    with psycopg.connect(server.get_uri(database="postgres"), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'itm_tutor'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE itm_tutor")
    return server.get_uri(database="itm_tutor"), server.cleanup


def reset_database() -> None:
    """Drop all rows and re-create the schema. Call at the start of each test."""
    from app.store import db

    db.reset_pool()
    db.init_db()
    with db.connection() as conn:
        conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
        conn.commit()


@pytest.fixture
def db_conn(postgres_url: str) -> Iterator[Conn]:
    from app.store import db

    reset_database()
    with db.connection() as conn:
        yield conn
    db.reset_pool()


SUPERUSER = {"username": "root", "password": "rootpassword"}


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


def make_learner(
    client: TestClient, username: str = "learner", password: str = "password1"
) -> str:
    """Register, admin-approve and log in a learner. Returns their bearer token."""
    assert (
        client.post(
            "/api/auth/register", json={"username": username, "password": password}
        ).status_code
        == 201
    )
    admin = login(client, **SUPERUSER)
    headers = {"Authorization": f"Bearer {admin}"}
    users = client.get("/api/users", headers=headers).json()
    user_id = next(u["id"] for u in users if u["username"] == username)
    assert (
        client.post(
            f"/api/users/{user_id}/status", json={"status": "approved"}, headers=headers
        ).status_code
        == 200
    )
    return login(client, username, password)


@pytest.fixture
def raw_client(postgres_url: str) -> Iterator[TestClient]:
    reset_database()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(raw_client: TestClient) -> TestClient:
    """A TestClient already authenticated as an approved learner."""
    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client)}"
    return raw_client


ROLES: tuple[Role, ...] = ("practitioner", "analyst", "academic")
PRIOR_EXPERIENCES: tuple[PriorExperience, ...] = ("none", "low", "moderate", "high")
GOALS: tuple[Goal, ...] = ("certification", "applied_competence", "orientation")
STUDY_TIMES: tuple[StudyTime, ...] = ("under_2h", "2_to_4h", "over_4h")
LEARNER_TYPES: tuple[LearnerType, ...] = ("visuell", "auditiv", "kommunikativ", "motorisch")


@pytest.fixture(scope="session")
def ruleset() -> RuleSet:
    return load_ruleset(RULES_DIR / "ruleset.v1.yaml")


@pytest.fixture(scope="session")
def catalogue() -> ClauseCatalogue:
    return load_catalogue(RULES_DIR / "clauses.v1.yaml")


@pytest.fixture(scope="session")
def planner_table() -> PlannerTable:
    return load_planner_table(RULES_DIR / "planner.v1.yaml")


@pytest.fixture(scope="session")
def step_templates() -> StepTemplates:
    return load_step_templates(RULES_DIR / "step_templates.v1.yaml")


@pytest.fixture(scope="session")
def curriculum() -> list[Chapter]:
    return extract_curriculum(BOOK_PATH)


def make_profile(
    role: Role = "practitioner",
    prior_experience: PriorExperience = "none",
    goal: Goal = "certification",
    study_time: StudyTime = "under_2h",
    learner_type: LearnerType = "kommunikativ",
    learner_id: str = "test-learner",
) -> Profile:
    return Profile(
        learner_id=learner_id,
        role=role,
        prior_experience=prior_experience,
        goal=goal,
        study_time=study_time,
        learner_type=learner_type,
        ruleset_version="v1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def all_profiles() -> list[Profile]:
    return [
        make_profile(role=role, prior_experience=exp, goal=goal, study_time=study, learner_type=lt)
        for role in ROLES
        for exp in PRIOR_EXPERIENCES
        for goal in GOALS
        for study in STUDY_TIMES
        for lt in LEARNER_TYPES
    ]
