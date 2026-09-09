from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.planner import LessonStep, PlanRationale
from app.core.vector import ControlVector
from app.store.db import Conn

LessonStatus = Literal["active", "completed", "abandoned"]


class LessonPlan(BaseModel):
    """The plan core.planner.plan_lesson() produced, plus the identity and
    timestamp the caller assigns (see plan_lesson's docstring for why those
    two live outside the pure planner: `datetime` can't be imported into
    core/planner.py at all under invariant 1's purity test, not even for a
    type annotation)."""

    model_config = ConfigDict(frozen=True)

    lesson_id: str
    learner_id: str
    conversation_id: str
    ruleset_version: str
    planner_version: str
    chapter_ref: str
    section_ref: str | None
    vector_snapshot: ControlVector
    steps: list[LessonStep]
    created_at: datetime


class StoredLessonPlan(LessonPlan):
    """A lesson plan as persisted: the immutable plan plus its live
    progress pointer and status. `rationale` is reproduced verbatim from
    plan time, same as every other plan field."""

    rationale: PlanRationale
    current_step: int
    status: LessonStatus


class LessonRepository:
    """Stored lesson plans: one row per plan, one row per step.

    A plan is immutable once created (invariant-6 spirit extended to lesson
    plans): `create` is the only way `steps`/`rationale`/`vector_snapshot`
    are written. `advance` only ever moves `current_step` forward and, once
    it reaches the final (recap) step, flips `status` to `completed`.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def create(
        self,
        *,
        lesson_id: str,
        learner_id: str,
        conversation_id: str,
        ruleset_version: str,
        planner_version: str,
        chapter_ref: str,
        section_ref: str | None,
        vector_snapshot: ControlVector,
        steps: list[LessonStep],
        rationale: PlanRationale,
    ) -> StoredLessonPlan:
        self._conn.execute(
            """
            INSERT INTO lesson_plans
                (lesson_id, learner_id, conversation_id, ruleset_version, planner_version,
                 chapter_ref, section_ref, vector_snapshot)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                lesson_id,
                learner_id,
                conversation_id,
                ruleset_version,
                planner_version,
                chapter_ref,
                section_ref,
                json.dumps(vector_snapshot.model_dump()),
            ),
        )
        for step in steps:
            self._conn.execute(
                """
                INSERT INTO lesson_steps
                    (lesson_id, index, kind, section_ref, page_start, page_end, rationale)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    lesson_id,
                    step.index,
                    step.kind,
                    step.section_ref,
                    step.page_start,
                    step.page_end,
                    rationale[step.index],
                ),
            )
        self._conn.commit()
        plan = self.get(lesson_id)
        assert plan is not None
        return plan

    _PLAN_COLUMNS = (
        "lesson_id, learner_id, conversation_id, ruleset_version, planner_version, "
        "chapter_ref, section_ref, vector_snapshot, current_step, status, created_at"
    )

    def _row_to_plan(self, row: dict) -> StoredLessonPlan:  # type: ignore[type-arg]
        steps_rows = self._conn.execute(
            "SELECT index, kind, section_ref, page_start, page_end, rationale "
            "FROM lesson_steps WHERE lesson_id = %s ORDER BY index",
            (row["lesson_id"],),
        ).fetchall()
        steps = [
            LessonStep(
                index=r["index"],
                kind=r["kind"],
                section_ref=r["section_ref"],
                page_start=r["page_start"],
                page_end=r["page_end"],
            )
            for r in steps_rows
        ]
        rationale = {r["index"]: r["rationale"] for r in steps_rows}
        return StoredLessonPlan(
            lesson_id=row["lesson_id"],
            learner_id=row["learner_id"],
            conversation_id=row["conversation_id"],
            ruleset_version=row["ruleset_version"],
            planner_version=row["planner_version"],
            chapter_ref=row["chapter_ref"],
            section_ref=row["section_ref"],
            vector_snapshot=ControlVector.model_validate(json.loads(row["vector_snapshot"])),
            steps=steps,
            rationale=rationale,
            current_step=row["current_step"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def get(self, lesson_id: str) -> StoredLessonPlan | None:
        row = self._conn.execute(
            f"SELECT {self._PLAN_COLUMNS} FROM lesson_plans WHERE lesson_id = %s",
            (lesson_id,),
        ).fetchone()
        return None if row is None else self._row_to_plan(row)

    def get_by_conversation(self, conversation_id: str) -> StoredLessonPlan | None:
        row = self._conn.execute(
            f"SELECT {self._PLAN_COLUMNS} FROM lesson_plans WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()
        return None if row is None else self._row_to_plan(row)

    def advance(self, lesson_id: str) -> StoredLessonPlan | None:
        """Moves `current_step` to the next step, marking the plan
        `completed` once that step is the final (recap) one. A no-op past
        the end -- callers check `current_step`/`status` before calling."""
        plan = self.get(lesson_id)
        if plan is None or plan.current_step >= len(plan.steps) - 1:
            return plan
        next_step = plan.current_step + 1
        status: LessonStatus = "completed" if next_step == len(plan.steps) - 1 else plan.status
        self._conn.execute(
            "UPDATE lesson_plans SET current_step = %s, status = %s WHERE lesson_id = %s",
            (next_step, status, lesson_id),
        )
        self._conn.commit()
        return self.get(lesson_id)

    def abandon(self, lesson_id: str) -> StoredLessonPlan | None:
        self._conn.execute(
            "UPDATE lesson_plans SET status = 'abandoned' WHERE lesson_id = %s", (lesson_id,)
        )
        self._conn.commit()
        return self.get(lesson_id)
