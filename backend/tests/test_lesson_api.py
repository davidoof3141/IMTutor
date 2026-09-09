import pytest
from fastapi.testclient import TestClient

from app.llm.client import TutorResponse
from tests.conftest import make_learner


def _onboard(client: TestClient, **overrides: str) -> dict:
    body = {
        "role": "practitioner",
        "prior_experience": "low",
        "goal": "certification",
        "study_time": "under_2h",
        "learner_type": "visuell",
    }
    body.update(overrides)
    response = client.post("/api/onboarding", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _set_training_mode(client: TestClient, learner_id: str, chapter_number: str = "1") -> None:
    r = client.put(
        f"/api/mode/{learner_id}",
        json={"mode": "training", "chapter_number": chapter_number, "section_number": None},
    )
    assert r.status_code == 200, r.text


def _stub_llm(monkeypatch: pytest.MonkeyPatch, texts: list[str] | None = None):
    """Each call to complete_turn returns the next text in `texts` (cycling
    the last one if calls outrun the list)."""
    calls: list[dict] = []

    def fake_complete(**kwargs: object):
        calls.append(kwargs)
        index = min(len(calls) - 1, len(texts) - 1) if texts else 0
        text = texts[index] if texts else f"step reply {len(calls)}"
        return TutorResponse(
            text=text, model="test/model", prompt_tokens=5, completion_tokens=5
        )

    monkeypatch.setattr("app.api.lesson.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.lesson.complete_turn", fake_complete)
    return calls


def _create_lesson(client: TestClient, learner_id: str) -> dict:
    r = client.post(f"/api/lesson/{learner_id}")
    assert r.status_code == 201, r.text
    return r.json()


def test_create_lesson_requires_training_mode_with_chapter(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    r = client.post(f"/api/lesson/{learner_id}")
    assert r.status_code == 400


def test_create_lesson_runs_step_zero_with_no_learner_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch, ["Hallo, lass uns anfangen."])
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)

    body = _create_lesson(client, learner_id)
    assert body["message"] == "Hallo, lass uns anfangen."
    assert body["current_step"] == 0
    assert body["status"] == "active"
    assert body["plan"]["steps"][0]["index"] == 0
    assert set(body["rationale"].keys()) == {str(s["index"]) for s in body["plan"]["steps"]}

    conversation_id = body["plan"]["conversation_id"]
    messages = client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()
    assert len(messages) == 1
    assert messages[0]["role"] == "tutor"
    assert messages[0]["text"] == "Hallo, lass uns anfangen."


def test_get_lesson_by_conversation_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    created = _create_lesson(client, learner_id)
    conversation_id = created["plan"]["conversation_id"]

    r = client.get(f"/api/lesson/{conversation_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["lesson_id"] == created["plan"]["lesson_id"]
    assert body["current_step"] == 0
    assert body["vector_drifted"] is False
    assert body["message"] is None


def test_advance_moves_the_pointer_and_appends_a_tutor_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch, ["step 0 reply", "step 1 reply"])
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    created = _create_lesson(client, learner_id)
    conversation_id = created["plan"]["conversation_id"]

    r = client.post(f"/api/lesson/{conversation_id}/advance")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_step"] == 1
    assert body["message"] == "step 1 reply"

    messages = client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()
    assert [m["text"] for m in messages] == ["step 0 reply", "step 1 reply"]
    assert all(m["role"] == "tutor" for m in messages)


def test_advance_past_the_last_step_is_conflict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    created = _create_lesson(client, learner_id)
    conversation_id = created["plan"]["conversation_id"]
    total_steps = len(created["plan"]["steps"])

    for _ in range(total_steps - 1):
        r = client.post(f"/api/lesson/{conversation_id}/advance")
        assert r.status_code == 200, r.text

    final = client.get(f"/api/lesson/{conversation_id}").json()
    assert final["status"] == "completed"
    assert final["current_step"] == total_steps - 1

    r = client.post(f"/api/lesson/{conversation_id}/advance")
    assert r.status_code == 409


def test_abandon_marks_the_lesson_and_blocks_further_advance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    created = _create_lesson(client, learner_id)
    conversation_id = created["plan"]["conversation_id"]

    r = client.post(f"/api/lesson/{conversation_id}/abandon")
    assert r.status_code == 200
    assert r.json()["status"] == "abandoned"

    r = client.post(f"/api/lesson/{conversation_id}/advance")
    assert r.status_code == 409


def test_lesson_requires_ownership(raw_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_llm(monkeypatch)
    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'alice', 'password1')}"
    alice_id = _onboard(raw_client)["profile"]["learner_id"]
    _set_training_mode(raw_client, alice_id)
    created = _create_lesson(raw_client, alice_id)
    conversation_id = created["plan"]["conversation_id"]

    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'bob', 'password1')}"
    _onboard(raw_client)
    assert raw_client.get(f"/api/lesson/{conversation_id}").status_code == 403
    assert raw_client.post(f"/api/lesson/{conversation_id}/advance").status_code == 403
    assert raw_client.post(f"/api/lesson/{conversation_id}/abandon").status_code == 403


def test_turn_log_carries_lesson_id_step_index_and_step_kind(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch, ["step 0", "step 1"])
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    created = _create_lesson(client, learner_id)
    conversation_id = created["plan"]["conversation_id"]
    client.post(f"/api/lesson/{conversation_id}/advance")

    log = client.get(f"/api/export/{learner_id}").json()
    assert len(log) == 2
    assert log[0]["lesson_id"] == created["plan"]["lesson_id"]
    assert log[0]["step_index"] == 0
    assert log[0]["step_kind"] == created["plan"]["steps"][0]["kind"]
    assert log[1]["step_index"] == 1


def test_free_text_turn_in_a_lesson_thread_tags_lesson_id_with_no_step(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)

    def fake_stream(**kwargs: object):
        yield "ok"
        yield TutorResponse(text="ok", model="test/model", prompt_tokens=1, completion_tokens=1)

    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.stream_turn", fake_stream)

    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    created = _create_lesson(client, learner_id)
    conversation_id = created["plan"]["conversation_id"]

    client.post(
        f"/api/chat/{learner_id}",
        json={"message": "Kannst du das nochmal erklaeren?", "conversation_id": conversation_id},
    )

    log = client.get(f"/api/export/{learner_id}").json()
    free_text_entry = log[-1]
    assert free_text_entry["lesson_id"] == created["plan"]["lesson_id"]
    assert free_text_entry["step_index"] is None
    assert free_text_entry["step_kind"] is None


def test_plan_is_immutable_across_overrides_and_advances(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch, ["a", "b", "c"])
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    created = _create_lesson(client, learner_id)
    conversation_id = created["plan"]["conversation_id"]

    original_steps = created["plan"]["steps"]
    original_vector = created["plan"]["vector_snapshot"]

    r = client.put(
        f"/api/config/{learner_id}/override", json={"pacing": 1, "explanation_depth": 5}
    )
    assert r.status_code == 200

    client.post(f"/api/lesson/{conversation_id}/advance")

    after = client.get(f"/api/lesson/{conversation_id}").json()
    assert after["plan"]["steps"] == original_steps
    assert after["plan"]["vector_snapshot"] == original_vector
    assert after["vector_drifted"] is True


def test_no_feedback_wrong_checkpoint_answers_do_not_change_the_plan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant-6 regression test for the lesson layer: driving a lesson
    with deliberately wrong checkpoint answers produces the exact same step
    list as one driven with correct answers -- the planner never sees
    checkpoint content, so nothing it produces can depend on it."""
    _stub_llm(monkeypatch)

    def fake_stream(**kwargs: object):
        yield "ok"
        yield TutorResponse(text="ok", model="test/model", prompt_tokens=1, completion_tokens=1)

    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.stream_turn", fake_stream)

    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id)
    wrong_run = _create_lesson(client, learner_id)
    wrong_conversation_id = wrong_run["plan"]["conversation_id"]
    client.post(
        f"/api/chat/{learner_id}",
        json={"message": "42, keine Ahnung", "conversation_id": wrong_conversation_id},
    )
    client.post(f"/api/lesson/{wrong_conversation_id}/advance")

    correct_run = _create_lesson(client, learner_id)
    correct_conversation_id = correct_run["plan"]["conversation_id"]
    client.post(
        f"/api/chat/{learner_id}",
        json={
            "message": "Die richtige, sorgfältig begründete Antwort.",
            "conversation_id": correct_conversation_id,
        },
    )
    client.post(f"/api/lesson/{correct_conversation_id}/advance")

    assert wrong_run["plan"]["steps"] == correct_run["plan"]["steps"]
    assert wrong_run["rationale"] == correct_run["rationale"]
