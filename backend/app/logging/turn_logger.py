import hashlib
from datetime import UTC, datetime
from typing import Any

from app.core.vector import ControlVector


def build_turn_log(
    *,
    learner_id: str,
    ruleset_version: str,
    effective_vector: ControlVector,
    system_prompt: str,
    book_context: str = "",
    study_mode: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    model: str,
    temperature: float,
    prompt: str,
    completion: str,
    prompt_tokens: int,
    completion_tokens: int,
    lesson_id: str | None = None,
    step_index: int | None = None,
    step_kind: str | None = None,
) -> dict[str, Any]:
    return {
        "learner_id": learner_id,
        "ruleset_version": ruleset_version,
        "effective_vector": effective_vector.model_dump(),
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "book_context": book_context,
        "study_mode": study_mode,
        "conversation_id": conversation_id,
        "model": model,
        "temperature": temperature,
        "prompt": prompt,
        "completion": completion,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        # null for free-text turns in a lesson thread and for exploration
        # turns -- only set when this turn ran a specific lesson step.
        "lesson_id": lesson_id,
        "step_index": step_index,
        "step_kind": step_kind,
        "timestamp": datetime.now(UTC).isoformat(),
    }
