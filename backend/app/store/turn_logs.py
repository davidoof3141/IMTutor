import json
from typing import Any

from app.store.db import Conn


class TurnLogRepository:
    """Append-only store for turn logs -- the evaluation dataset.

    Treated as a deliverable, not debug output: rows are only ever inserted,
    never updated or deleted.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def append(self, record: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO turn_logs (learner_id, payload) VALUES (%s, %s)",
            (record["learner_id"], json.dumps(record)),
        )
        self._conn.commit()

    def read_all(self, learner_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload FROM turn_logs WHERE learner_id = %s ORDER BY id",
            (learner_id,),
        ).fetchall()
        return [row["payload"] for row in rows]
