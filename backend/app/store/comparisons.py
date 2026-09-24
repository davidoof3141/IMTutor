import json
import uuid
from typing import Any, Literal

from app.store.db import Conn

# Which control vector produced a variant's text.
VariantKind = Literal["personalized", "generic"]
# Which on-screen slot ("Antwort A" / "Antwort B") a variant landed in -- assigned
# randomly per turn (see api/chat.py) so position never correlates with kind.
VariantLabel = Literal["a", "b"]
ReasonTag = Literal["detail", "tone", "clarity", "examples", "difficulty", "other"]

_COLUMNS = (
    "id, conversation_id, learner_id, learner_message, ruleset_version, "
    "personalized_vector, baseline_vector, variant_a_kind, variant_b_kind, "
    "variant_a_text, variant_a_model, variant_a_prompt_tokens, variant_a_completion_tokens, "
    "variant_b_text, variant_b_model, variant_b_prompt_tokens, variant_b_completion_tokens, "
    "book_context, book_image_refs, page_refs, attachment_ids, lesson_id, study_mode, "
    "chosen_variant, decided_at"
)


class ComparisonRepository:
    """The personalized-vs-generic A/B turns shown to link-invited accounts
    (see app/api/chat.py's /compare and /compare/{id}/choose routes).

    A row is created empty (both variant texts NULL) the moment a comparison
    turn starts, filled in as each variant's stream finishes, and finalized
    -- reasons + which one won -- when the learner picks. Nothing here is
    exposed directly to the frontend; it exists so /choose can turn the pick
    into the same conversation-history turn a normal chat message would
    produce, and so the comparison itself is preserved for evaluation.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def create_pending(
        self,
        *,
        conversation_id: str,
        learner_id: str,
        learner_message: str,
        ruleset_version: str,
        personalized_vector: dict[str, Any],
        baseline_vector: dict[str, Any],
        variant_a_kind: VariantKind,
        variant_b_kind: VariantKind,
        book_context: str,
        book_image_refs: list[tuple[str, int]],
        page_refs: list[int],
        attachment_ids: list[str],
        lesson_id: str | None,
        study_mode: dict[str, Any] | None,
    ) -> str:
        comparison_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO answer_comparisons (
                id, conversation_id, learner_id, learner_message, ruleset_version,
                personalized_vector, baseline_vector, variant_a_kind, variant_b_kind,
                book_context, book_image_refs, page_refs, attachment_ids,
                lesson_id, study_mode
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                comparison_id,
                conversation_id,
                learner_id,
                learner_message,
                ruleset_version,
                json.dumps(personalized_vector),
                json.dumps(baseline_vector),
                variant_a_kind,
                variant_b_kind,
                book_context,
                json.dumps(book_image_refs),
                json.dumps(page_refs),
                json.dumps(attachment_ids),
                lesson_id,
                json.dumps(study_mode) if study_mode is not None else None,
            ),
        )
        self._conn.commit()
        return comparison_id

    def record_variant_result(
        self,
        comparison_id: str,
        label: VariantLabel,
        *,
        text: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        # label is one of the two literals above -- never request input -- so
        # interpolating it into the column name here is not an injection risk.
        assert label in ("a", "b")
        self._conn.execute(
            f"""
            UPDATE answer_comparisons
            SET variant_{label}_text = %s, variant_{label}_model = %s,
                variant_{label}_prompt_tokens = %s, variant_{label}_completion_tokens = %s
            WHERE id = %s
            """,
            (text, model, prompt_tokens, completion_tokens, comparison_id),
        )
        self._conn.commit()

    def get_pending(self, comparison_id: str, learner_id: str) -> dict[str, Any] | None:
        """The row for a not-yet-decided comparison owned by this learner, or
        None if it doesn't exist, belongs to someone else, or is already
        decided."""
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM answer_comparisons "
            "WHERE id = %s AND learner_id = %s AND decided_at IS NULL",
            (comparison_id, learner_id),
        ).fetchone()
        return dict(row) if row is not None else None

    def kind_preference_counts(self) -> list[dict[str, Any]]:
        """How often each kind (personalized/generic) was the one picked,
        across every decided comparison -- for the admin stats view."""
        rows = self._conn.execute(
            """
            SELECT
                CASE WHEN chosen_variant = 'a' THEN variant_a_kind ELSE variant_b_kind END AS kind,
                COUNT(*) AS count
            FROM answer_comparisons
            WHERE decided_at IS NOT NULL
            GROUP BY kind
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def reason_counts(self) -> list[dict[str, Any]]:
        """How often each reason tag was picked (a decided turn can carry
        more than one), across every decided comparison."""
        rows = self._conn.execute(
            """
            SELECT reason, COUNT(*) AS count
            FROM answer_comparisons, jsonb_array_elements_text(reasons) AS reason
            WHERE decided_at IS NOT NULL
            GROUP BY reason
            ORDER BY count DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def decided_and_pending_counts(self) -> tuple[int, int]:
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE decided_at IS NOT NULL) AS decided,
                COUNT(*) FILTER (WHERE decided_at IS NULL) AS pending
            FROM answer_comparisons
            """
        ).fetchone()
        assert row is not None
        return row["decided"], row["pending"]

    def finalize(
        self,
        comparison_id: str,
        *,
        chosen_variant: VariantLabel,
        reasons: list[ReasonTag],
        other_reason: str | None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE answer_comparisons
            SET chosen_variant = %s, reasons = %s, other_reason = %s, decided_at = now()
            WHERE id = %s
            """,
            (chosen_variant, json.dumps(reasons), other_reason, comparison_id),
        )
        self._conn.commit()
