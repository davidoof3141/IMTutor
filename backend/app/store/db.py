"""Postgres connection pool and schema.

The whole app talks to one Postgres database via a process-wide connection
pool. Schema is created once (`ensure_schema`) rather than per request -- every
table lives in `_SCHEMA` below, `CREATE TABLE IF NOT EXISTS` so running it again
against an existing database is a no-op. Startup tries it once; if the database
is unreachable then (Neon compute asleep, bad `DATABASE_URL`), the first request
that does reach the database runs it instead, so a cold start against a sleeping
DB no longer dark-404s the whole API.
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger("app.db")

Conn = psycopg.Connection[DictRow]

DEFAULT_DATABASE_URL = "postgresql://itm:itm@localhost:5432/itm_tutor"

# psycopg_pool raises PoolTimeout with this generic message whenever it can't
# hand out a connection -- the real reason (auth failure, TLS rejection, host
# unreachable) is swallowed by its background worker. Keep the wait short so a
# request against a down database fails fast instead of hanging for 30s.
_POOL_TIMEOUT = float(os.environ.get("DB_POOL_TIMEOUT", "10"))
_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "10"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'learner' CHECK (role IN ('admin', 'learner')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    -- Bumped whenever an admin changes this account's role or status; the
    -- value is baked into every login token and re-checked on each request,
    -- so a demotion or rejection invalidates tokens already in the wild.
    token_version INTEGER NOT NULL DEFAULT 0,
    -- Set when an admin hands out a one-time password; the account is barred
    -- from everything except changing its password until it is cleared.
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Poor-man's migration for databases created before these columns existed.
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS profiles (
    learner_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    role TEXT NOT NULL,
    prior_experience TEXT NOT NULL,
    goal TEXT NOT NULL,
    industry TEXT NOT NULL,
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

-- industry replaced study_time in onboarding. Old rows backfill to
-- 'neutral' (branchenneutral), which is also the rule set's default
-- example_domain, so a pre-existing profile keeps the prompt it had.
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS industry TEXT NOT NULL DEFAULT 'neutral';
-- study_time is no longer written; kept (nullable) rather than dropped so the
-- column's history survives for anyone analysing older cohorts. Guarded
-- because a database created after this change has no such column at all,
-- and ALTER COLUMN has no IF EXISTS form.
DO $$
BEGIN
    ALTER TABLE profiles ALTER COLUMN study_time DROP NOT NULL;
EXCEPTION
    WHEN undefined_column THEN NULL;
END $$;

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

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS book_chunks (
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    page INTEGER NOT NULL,
    embedding vector(1536) NOT NULL
);

CREATE INDEX IF NOT EXISTS book_chunks_embedding_idx
    ON book_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS turn_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    learner_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS turn_logs_learner_idx ON turn_logs (learner_id, id);

-- Fixed-window counters for abuse protection on unauthenticated endpoints
-- (login, register). One row per (action, client) bucket; the window rolls
-- over lazily on the next hit rather than via a sweep. Shared across
-- processes so it also holds on serverless, where in-memory counters don't.
CREATE TABLE IF NOT EXISTS rate_limits (
    bucket TEXT PRIMARY KEY,
    window_start TIMESTAMPTZ NOT NULL DEFAULT now(),
    count INTEGER NOT NULL DEFAULT 0
);
"""

_pool: "ConnectionPool[Conn] | None" = None
_schema_ready = False


_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "db"}


def database_url() -> str:
    """The configured URL, with `sslmode=require` forced for remote hosts.

    Neon (and every hosted Postgres) refuses plaintext connections; a URL that
    omits `sslmode` is a common cause of connections that only fail once
    deployed. Local/compose databases are left untouched.
    """
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    try:
        params = conninfo_to_dict(url)
    except psycopg.ProgrammingError:
        return url  # let psycopg surface the parse error itself
    host = str(params.get("host", ""))
    is_local = host in _LOCAL_HOSTS or host.startswith("/")  # "/" -> unix socket
    if is_local or "sslmode" in params:
        return url
    return make_conninfo(url, sslmode="require")


def get_pool() -> "ConnectionPool[Conn]":
    """Process-wide connection pool, opened on first use."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            database_url(),
            min_size=1,
            max_size=10,
            timeout=_POOL_TIMEOUT,
            connection_class=psycopg.Connection[DictRow],
            kwargs={"row_factory": dict_row, "connect_timeout": _CONNECT_TIMEOUT},
            # Neon (and any pooler) drops idle server connections; without a
            # check the pool can hand out a dead one after the compute slept.
            check=ConnectionPool.check_connection,
            open=True,
        )
    return _pool


def reset_pool() -> None:
    """Close the pool so the next `get_pool()` reconnects. Used by tests."""
    global _pool, _schema_ready
    if _pool is not None:
        _pool.close()
        _pool = None
    _schema_ready = False


@contextmanager
def connection() -> Iterator[Conn]:
    """Borrow a connection from the pool for the duration of one request."""
    with get_pool().connection() as conn:
        yield conn


def init_db() -> None:
    """Create every table if it does not exist. Safe to run repeatedly."""
    global _schema_ready
    with connection() as conn:
        conn.execute(_SCHEMA)
        conn.commit()
    _schema_ready = True


def ensure_schema() -> None:
    """Run schema + superuser setup once per process, on the first call that
    reaches the DB.

    Startup does this too, but tolerates failure (see `main.lifespan`); this is
    the retry path for a process that booted while the database was down.
    """
    if _schema_ready:
        return
    init_db()
    seed_superuser()


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
