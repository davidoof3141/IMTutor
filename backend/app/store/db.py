"""Postgres connection pool and schema.

The whole app talks to one Postgres database via a process-wide connection
pool. Schema is created once at startup (`init_db`) rather than per request --
every table lives in `_SCHEMA` below, `CREATE TABLE IF NOT EXISTS` so a restart
against an existing database is a no-op.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

Conn = psycopg.Connection[DictRow]

DEFAULT_DATABASE_URL = "postgresql://itm:itm@localhost:5432/itm_tutor"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'learner' CHECK (role IN ('admin', 'learner')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profiles (
    learner_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    role TEXT NOT NULL,
    prior_experience TEXT NOT NULL,
    goal TEXT NOT NULL,
    study_time TEXT NOT NULL,
    learner_type TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Poor-man's migration for a database created before learner_type existed --
-- CREATE TABLE IF NOT EXISTS above is a no-op against an existing table, so
-- an already-running deployment needs this to pick the column up. The
-- default only backfills old rows; every new insert passes an explicit
-- value (learner_type has no default at the application layer).
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS learner_type TEXT NOT NULL DEFAULT 'kommunikativ';

CREATE TABLE IF NOT EXISTS overrides (
    learner_id TEXT NOT NULL,
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (learner_id, field)
);

CREATE TABLE IF NOT EXISTS study_mode (
    learner_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    chapter_number TEXT,
    section_number TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    learner_id TEXT PRIMARY KEY,
    model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    title TEXT,
    mode TEXT,
    chapter_number TEXT,
    section_number TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS conversations_learner_idx
    ON conversations (learner_id, last_message_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('learner', 'tutor')),
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_conversation_idx
    ON messages (conversation_id, id);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('image', 'document')),
    size_bytes INTEGER NOT NULL,
    data BYTEA NOT NULL,
    extracted_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS attachments_conversation_idx ON attachments (conversation_id);
CREATE INDEX IF NOT EXISTS attachments_message_idx ON attachments (message_id);

CREATE TABLE IF NOT EXISTS message_book_images (
    message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    image_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    PRIMARY KEY (message_id, image_id)
);

CREATE TABLE IF NOT EXISTS message_page_refs (
    message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    PRIMARY KEY (message_id, page)
);

CREATE TABLE IF NOT EXISTS lesson_plans (
    lesson_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    ruleset_version TEXT NOT NULL,
    planner_version TEXT NOT NULL,
    chapter_ref TEXT NOT NULL,
    section_ref TEXT,
    vector_snapshot TEXT NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS lesson_plans_conversation_idx
    ON lesson_plans (conversation_id);

CREATE TABLE IF NOT EXISTS lesson_steps (
    lesson_id TEXT NOT NULL REFERENCES lesson_plans(lesson_id) ON DELETE CASCADE,
    index INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('explain', 'example', 'checkpoint', 'recap')),
    section_ref TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    PRIMARY KEY (lesson_id, index)
);
"""

_pool: "ConnectionPool[Conn] | None" = None


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_pool() -> "ConnectionPool[Conn]":
    """Process-wide connection pool, opened on first use."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            database_url(),
            min_size=1,
            max_size=10,
            connection_class=psycopg.Connection[DictRow],
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def reset_pool() -> None:
    """Close the pool so the next `get_pool()` reconnects. Used by tests."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[Conn]:
    """Borrow a connection from the pool for the duration of one request."""
    with get_pool().connection() as conn:
        yield conn


def init_db() -> None:
    """Create every table if it does not exist. Safe to run on every startup."""
    with connection() as conn:
        conn.execute(_SCHEMA)
        conn.commit()


def seed_superuser() -> None:
    """Ensure the .env-configured superuser exists as an approved admin.

    Only creates it when the username is absent -- an existing account (and its
    password) is never touched.
    """
    from app.security import hash_password

    username = os.environ.get("SUPERUSER_USERNAME")
    password = os.environ.get("SUPERUSER_PASSWORD")
    if not username or not password:
        return

    import uuid

    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = %s", (username,)
        ).fetchone()
        if row is not None:
            return
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, role, status)
            VALUES (%s, %s, %s, 'admin', 'approved')
            """,
            (str(uuid.uuid4()), username, hash_password(password)),
        )
        conn.commit()
