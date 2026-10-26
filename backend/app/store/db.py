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

-- One login link per user: a high-entropy token (only its hash is stored,
-- same treatment as a password) that logs its owner in without a password.
-- Re-issuing (see LoginLinkRepository.issue) overwrites the row, so an old
-- link stops working the moment a new one is generated.
CREATE TABLE IF NOT EXISTS login_links (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Shared "group" sign-up links: one token that lets up to max_uses people each
-- create their own link-invited account (see GroupLinkRepository). Only the
-- token's hash is stored. uses is bumped atomically on every claim, so the
-- cap holds under concurrent requests.
CREATE TABLE IF NOT EXISTS group_links (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL DEFAULT '',
    max_uses INTEGER NOT NULL CHECK (max_uses > 0),
    uses INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS group_link_id TEXT;

CREATE TABLE IF NOT EXISTS profiles (
    learner_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    -- mapping inputs
    prior_knowledge_seed TEXT NOT NULL,
    learning_goal TEXT NOT NULL,
    retention_horizon TEXT NOT NULL,
    industry TEXT NOT NULL,
    -- preferences (prompt assembly only; not mapping inputs)
    simplified_language BOOLEAN NOT NULL,
    presentation_style TEXT NOT NULL,
    learner_type TEXT NOT NULL DEFAULT 'none',
    ruleset_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Poor-man's migration for databases created before the onboarding rework
-- (CREATE TABLE IF NOT EXISTS above is a no-op against an existing table).
-- The new columns get defaults that only backfill old rows; every insert
-- passes explicit values. role no longer feeds any parameter and is kept
-- (nullable) rather than dropped, so older cohorts stay
-- analysable; prior_experience/goal are carried over below.
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS industry TEXT NOT NULL DEFAULT 'neutral';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS prior_knowledge_seed TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS learning_goal TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS retention_horizon TEXT NOT NULL DEFAULT '1_to_3_months';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS simplified_language BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS presentation_style TEXT NOT NULL DEFAULT 'balanced';
-- learner_type returned as a prompt-only preference. Legacy tables already have the
-- (nullable) column, so this is a no-op there; databases created between the
-- onboarding rework and this change get it here.
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS learner_type TEXT NOT NULL DEFAULT 'none';
DO $$
BEGIN
    ALTER TABLE profiles ALTER COLUMN role DROP NOT NULL;
    ALTER TABLE profiles ALTER COLUMN learner_type DROP NOT NULL;
    ALTER TABLE profiles ALTER COLUMN prior_experience DROP NOT NULL;
    ALTER TABLE profiles ALTER COLUMN goal DROP NOT NULL;
    UPDATE profiles SET
        prior_knowledge_seed = prior_experience,
        learning_goal = CASE goal WHEN 'applied_competence' THEN 'applied' ELSE goal END
    WHERE prior_knowledge_seed IS NULL;
EXCEPTION
    WHEN undefined_column THEN NULL;
END $$;
ALTER TABLE profiles ALTER COLUMN prior_knowledge_seed SET NOT NULL;
ALTER TABLE profiles ALTER COLUMN learning_goal SET NOT NULL;

-- One row per (learner, chapter diagnostic): the answers, the score, and the
-- chapter-level prior knowledge they produced. Write-once like Profile -- a
-- diagnostic is not retaken, so the level can't be gamed by trial and error.
-- It is stored beside the profile, never in it: the seed stays untouched.
-- `override` holds the learner's per-field overrides of this chapter's vector
-- (DR6), set on the summary screen.
CREATE TABLE IF NOT EXISTS chapter_diagnostics (
    learner_id TEXT NOT NULL,
    diagnostic_key TEXT NOT NULL,
    answers JSONB NOT NULL,
    correct_count INTEGER NOT NULL,
    experience_seed TEXT NOT NULL,
    prior_knowledge TEXT NOT NULL,
    override JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (learner_id, diagnostic_key)
);

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

-- Append-only audit trail of scrutability-interface edits (see
-- app/store/override_changes.py): one row per field a learner actually
-- changed, set, or reverted, with the value on each side of the edit.
-- old_value/new_value are NULL when that side is "the derived default"
-- rather than an explicit override.
CREATE TABLE IF NOT EXISTS override_changes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    learner_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS override_changes_learner_idx
    ON override_changes (learner_id, id);

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

-- Per-step concreteness (planner v2 fading). NULL on plans made before v2:
-- those steps use the plan's vector concreteness unchanged.
ALTER TABLE lesson_steps ADD COLUMN IF NOT EXISTS concreteness INTEGER;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS book_chunks (
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    page INTEGER NOT NULL,
    embedding vector(1536) NOT NULL
);

CREATE INDEX IF NOT EXISTS book_chunks_embedding_idx
    ON book_chunks USING hnsw (embedding vector_cosine_ops);

-- Personalized-vs-generic A/B chat turns shown to link-invited accounts (see
-- app/store/comparisons.py). Created with both variant_*_text NULL the
-- moment a comparison starts, filled in as each stream finishes, and
-- finalized once the learner picks a favorite and a reason.
CREATE TABLE IF NOT EXISTS answer_comparisons (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    learner_id TEXT NOT NULL,
    learner_message TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    personalized_vector JSONB NOT NULL,
    baseline_vector JSONB NOT NULL,
    -- Which vector produced each on-screen slot -- randomized per turn so
    -- position never correlates with personalization.
    variant_a_kind TEXT NOT NULL CHECK (variant_a_kind IN ('personalized', 'generic')),
    variant_b_kind TEXT NOT NULL CHECK (variant_b_kind IN ('personalized', 'generic')),
    variant_a_text TEXT,
    variant_a_model TEXT,
    variant_a_prompt_tokens INTEGER,
    variant_a_completion_tokens INTEGER,
    variant_b_text TEXT,
    variant_b_model TEXT,
    variant_b_prompt_tokens INTEGER,
    variant_b_completion_tokens INTEGER,
    book_context TEXT NOT NULL DEFAULT '',
    book_image_refs JSONB NOT NULL DEFAULT '[]',
    page_refs JSONB NOT NULL DEFAULT '[]',
    attachment_ids JSONB NOT NULL DEFAULT '[]',
    lesson_id TEXT,
    study_mode JSONB,
    chosen_variant TEXT CHECK (chosen_variant IN ('a', 'b')),
    reasons JSONB,
    other_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS answer_comparisons_conversation_idx
    ON answer_comparisons (conversation_id, created_at);

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
