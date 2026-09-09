from typing import Literal

from pydantic import BaseModel

from app.store.db import Conn

Mode = Literal["exploration", "training"]

DEFAULT_STATE_MODE: Mode = "exploration"


class StudyModeState(BaseModel):
    mode: Mode
    chapter_number: str | None = None
    section_number: str | None = None


class StudyModeRepository:
    """Per-learner exploration/training mode and schedule selection.

    Not part of the control vector -- selecting a mode or chapter never
    touches derive()/effective(), it only shapes the extra context message
    chat.py adds to the LLM call (see app/rag/toc.py::format_focus).
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def get(self, learner_id: str) -> StudyModeState:
        row = self._conn.execute(
            "SELECT mode, chapter_number, section_number FROM study_mode WHERE learner_id = %s",
            (learner_id,),
        ).fetchone()
        if row is None:
            return StudyModeState(mode=DEFAULT_STATE_MODE)
        return StudyModeState(
            mode=row["mode"],
            chapter_number=row["chapter_number"],
            section_number=row["section_number"],
        )

    def set(self, learner_id: str, state: StudyModeState) -> StudyModeState:
        self._conn.execute(
            """
            INSERT INTO study_mode (learner_id, mode, chapter_number, section_number)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (learner_id) DO UPDATE SET
                mode = excluded.mode,
                chapter_number = excluded.chapter_number,
                section_number = excluded.section_number
            """,
            (learner_id, state.mode, state.chapter_number, state.section_number),
        )
        self._conn.commit()
        return state
