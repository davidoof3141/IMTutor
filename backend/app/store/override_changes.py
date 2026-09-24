import json
from typing import Any

from app.store.db import Conn


class OverrideChangeRepository:
    """Append-only audit trail of edits made in the scrutability interface
    (see app/api/config.py) -- one row per parameter a learner actually set
    or reverted, recording the value on each side of the change."""

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def log(
        self, learner_id: str, field: str, old_value: Any, new_value: Any
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO override_changes (learner_id, field, old_value, new_value)
            VALUES (%s, %s, %s, %s)
            """,
            (
                learner_id,
                field,
                json.dumps(old_value) if old_value is not None else None,
                json.dumps(new_value) if new_value is not None else None,
            ),
        )
        self._conn.commit()

    def field_counts(self) -> list[dict[str, Any]]:
        """How often each control-vector parameter was edited in the
        scrutability interface -- for the admin stats view."""
        rows = self._conn.execute(
            "SELECT field, COUNT(*) AS count FROM override_changes GROUP BY field ORDER BY count DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def total(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM override_changes").fetchone()
        assert row is not None
        return row["count"]
