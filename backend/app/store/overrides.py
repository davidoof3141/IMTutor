import json

from app.core.vector import Override
from app.store.db import Conn


class OverrideRepository:
    """Sparse per-learner override storage. One row per overridden field."""

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def get(self, learner_id: str) -> Override:
        rows = self._conn.execute(
            "SELECT field, value FROM overrides WHERE learner_id = %s", (learner_id,)
        ).fetchall()
        return {row["field"]: json.loads(row["value"]) for row in rows}

    def set(self, learner_id: str, override: Override) -> Override:
        for field, value in override.items():
            self._conn.execute(
                """
                INSERT INTO overrides (learner_id, field, value) VALUES (%s, %s, %s)
                ON CONFLICT (learner_id, field) DO UPDATE SET value = excluded.value
                """,
                (learner_id, field, json.dumps(value)),
            )
        self._conn.commit()
        return self.get(learner_id)

    def delete_field(self, learner_id: str, field: str) -> Override:
        self._conn.execute(
            "DELETE FROM overrides WHERE learner_id = %s AND field = %s", (learner_id, field)
        )
        self._conn.commit()
        return self.get(learner_id)

    def delete_all(self, learner_id: str) -> Override:
        self._conn.execute("DELETE FROM overrides WHERE learner_id = %s", (learner_id,))
        self._conn.commit()
        return self.get(learner_id)
