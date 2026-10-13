import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.clauses import ClauseCatalogue, load_catalogue
from app.core.planner import PlannerTable, load_planner_table
from app.core.profile import (
    Industry,
    LearnerType,
    LearningGoal,
    PresentationStyle,
    PriorKnowledge,
    Profile,
    RetentionHorizon,
)
from app.core.rules import RuleSet, load_ruleset
from app.core.step_templates import StepTemplates, load_step_templates
from app.rag.chunking import BOOK_PATH
from app.rag.toc import Chapter, extract_curriculum
from app.store.db import Conn

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"

_TABLES = (
    "users, login_links, profiles, overrides, override_changes, study_mode, sessions, "
    "conversations, messages, attachments, answer_comparisons, lesson_plans, lesson_steps, "
    "turn_logs, book_chunks, rate_limits"
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


PRIOR_KNOWLEDGES: tuple[PriorKnowledge, ...] = ("none", "low", "moderate", "high")
GOALS: tuple[LearningGoal, ...] = ("certification", "applied", "orientation")
RETENTION_HORIZONS: tuple[RetentionHorizon, ...] = (
    "within_2_weeks",
    "1_to_3_months",
    "long_term",
)
INDUSTRIES: tuple[Industry, ...] = (
    "manufacturing",
    "finance",
    "public_sector",
    "healthcare",
    "retail",
    "it_software",
    "logistics",
    "energy",
    "consulting",
    "neutral",
)


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
    prior_knowledge_seed: PriorKnowledge = "none",
    learning_goal: LearningGoal = "certification",
    retention_horizon: RetentionHorizon = "1_to_3_months",
    industry: Industry = "neutral",
    simplified_language: bool = False,
    presentation_style: PresentationStyle = "balanced",
    learner_type: LearnerType = "none",
    learner_id: str = "test-learner",
) -> Profile:
    return Profile(
        learner_id=learner_id,
        prior_knowledge_seed=prior_knowledge_seed,
        learning_goal=learning_goal,
        retention_horizon=retention_horizon,
        industry=industry,
        simplified_language=simplified_language,
        presentation_style=presentation_style,
        learner_type=learner_type,
        ruleset_version="v1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def all_profiles() -> list[Profile]:
    """The full mapping-input space (4 x 3 x 3 x 10 = 360). Preferences are not
    mapping inputs, so they are not enumerated."""
    return [
        make_profile(
            prior_knowledge_seed=pk, learning_goal=goal, retention_horizon=rh, industry=industry
        )
        for pk in PRIOR_KNOWLEDGES
        for goal in GOALS
        for rh in RETENTION_HORIZONS
        for industry in INDUSTRIES
    ]
