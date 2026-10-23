import json

import psycopg
from pydantic import BaseModel, ConfigDict

from app.core.profile import PriorKnowledge
from app.core.vector import Override
from app.store.db import Conn


class DiagnosticAlreadyTaken(Exception):
    pass


class StoredDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    learner_id: str
    diagnostic_key: str
    answers: list[int]
    correct_count: int
    experience_seed: PriorKnowledge
    prior_knowledge: PriorKnowledge  # the chapter-level result
    override: Override


class ChapterDiagnosticRepository:
    """Per-(learner, chapter) diagnostic results.

    The result row is write-once (no retake, no update of the score); only the
    sparse per-chapter `override` can change afterwards. It lives outside the
    Profile, so a diagnostic can never mutate the onboarding seed.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def create(self, stored: StoredDiagnostic) -> None:
        try:
            self._conn.execute(
                """
                INSERT INTO chapter_diagnostics
                    (learner_id, diagnostic_key, answers, correct_count,
                     experience_seed, prior_knowledge, override)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    stored.learner_id,
                    stored.diagnostic_key,
                    json.dumps(stored.answers),
                    stored.correct_count,
                    stored.experience_seed,
                    stored.prior_knowledge,
                    json.dumps(stored.override),
                ),
            )
            self._conn.commit()
        except psycopg.errors.UniqueViolation as exc:
            self._conn.rollback()
            raise DiagnosticAlreadyTaken(stored.diagnostic_key) from exc

    def get(self, learner_id: str, diagnostic_key: str) -> StoredDiagnostic | None:
        row = self._conn.execute(
            "SELECT * FROM chapter_diagnostics WHERE learner_id = %s AND diagnostic_key = %s",
            (learner_id, diagnostic_key),
        ).fetchone()
        if row is None:
            return None
        return StoredDiagnostic(
            learner_id=row["learner_id"],
            diagnostic_key=row["diagnostic_key"],
            answers=row["answers"],
            correct_count=row["correct_count"],
            experience_seed=row["experience_seed"],
            prior_knowledge=row["prior_knowledge"],
            override=row["override"],
        )

    def set_override(self, learner_id: str, diagnostic_key: str, override: Override) -> None:
        self._conn.execute(
            """
            UPDATE chapter_diagnostics SET override = %s
            WHERE learner_id = %s AND diagnostic_key = %s
            """,
            (json.dumps(override), learner_id, diagnostic_key),
        )
        self._conn.commit()

    def list_with_usernames(self) -> list[dict]:
        """Every stored result with the owning username, for the admin view."""
        return self._conn.execute(
            """
            SELECT u.username, d.diagnostic_key, d.correct_count,
                   d.experience_seed, d.prior_knowledge, d.created_at
            FROM chapter_diagnostics d
            JOIN profiles p ON p.learner_id = d.learner_id
            JOIN users u ON u.id = p.user_id
            ORDER BY u.username, d.created_at
            """
        ).fetchall()
