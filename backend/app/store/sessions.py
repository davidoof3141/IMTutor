from app.store.db import Conn


class SessionRepository:
    """Pins the LLM model per learner session.

    The model is chosen on the learner's first chat turn and reused for every
    subsequent turn, so a session's configuration can't silently drift if the
    default model changes mid-session.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def get_or_create(self, learner_id: str, requested_model: str) -> str:
        row = self._conn.execute(
            "SELECT model FROM sessions WHERE learner_id = %s", (learner_id,)
        ).fetchone()
        if row is not None:
            return str(row["model"])
        self._conn.execute(
            "INSERT INTO sessions (learner_id, model) VALUES (%s, %s)",
            (learner_id, requested_model),
        )
        self._conn.commit()
        return requested_model
