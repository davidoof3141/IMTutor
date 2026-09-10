import pytest
from fastapi.testclient import TestClient

from app.llm.client import TutorResponse
from tests.conftest import make_learner


def _onboard(client: TestClient) -> dict:
    response = client.post(
        "/api/onboarding",
        json={
            "role": "practitioner",
            "prior_experience": "low",
            "goal": "certification",
            "industry": "healthcare",
            "learner_type": "visuell",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _stub_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stream(**kwargs: object):
        yield "ok"
        yield TutorResponse(text="ok", model="test/model", prompt_tokens=1, completion_tokens=1)

    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.stream_turn", fake_stream)


def _stub_suggestions(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    def fake_complete(**kwargs: object):
        return TutorResponse(text=text, model="test/model", prompt_tokens=2, completion_tokens=6)

    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.complete_turn", fake_complete)


def _start_conversation(client: TestClient, learner_id: str) -> str:
    r = client.post(f"/api/chat/{learner_id}", json={"message": "Was ist Informationsmanagement?"})
    return r.headers["x-conversation-id"]


def test_suggestions_require_an_existing_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    r = client.post(
        f"/api/chat/{learner_id}/suggestions", json={"conversation_id": "does-not-exist"}
    )
    assert r.status_code == 404


def test_suggestions_require_a_non_empty_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    conversation_id = client.post(f"/api/conversations/{learner_id}").json()["id"]

    r = client.post(
        f"/api/chat/{learner_id}/suggestions", json={"conversation_id": conversation_id}
    )
    assert r.status_code == 400


def test_suggestions_returns_up_to_three_parsed_questions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_stream(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]
    conversation_id = _start_conversation(client, learner_id)

    _stub_suggestions(
        monkeypatch,
        "- Was bedeutet das für die Praxis?\n"
        "- Kannst du ein Beispiel geben?\n"
        "- Wie hängt das mit Kapitel 2 zusammen?\n",
    )
    r = client.post(
        f"/api/chat/{learner_id}/suggestions", json={"conversation_id": conversation_id}
    )
    assert r.status_code == 200, r.text
    assert r.json()["questions"] == [
        "Was bedeutet das für die Praxis?",
        "Kannst du ein Beispiel geben?",
        "Wie hängt das mit Kapitel 2 zusammen?",
    ]


def test_suggestions_are_not_persisted_as_a_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_stream(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]
    conversation_id = _start_conversation(client, learner_id)

    before = client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()
    _stub_suggestions(monkeypatch, "Frage eins?\nFrage zwei?\nFrage drei?")
    client.post(f"/api/chat/{learner_id}/suggestions", json={"conversation_id": conversation_id})
    after = client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()

    assert before == after


def test_suggestions_are_logged_with_the_conversation_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_stream(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]
    conversation_id = _start_conversation(client, learner_id)

    _stub_suggestions(monkeypatch, "Frage eins?\nFrage zwei?\nFrage drei?")
    client.post(f"/api/chat/{learner_id}/suggestions", json={"conversation_id": conversation_id})

    log = client.get(f"/api/export/{learner_id}").json()
    suggestions_entry = log[-1]
    assert suggestions_entry["conversation_id"] == conversation_id
    assert suggestions_entry["lesson_id"] is None


def test_suggestions_require_ownership(raw_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_stream(monkeypatch)
    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'alice', 'password1')}"
    alice_id = _onboard(raw_client)["profile"]["learner_id"]
    conversation_id = _start_conversation(raw_client, alice_id)

    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'bob', 'password1')}"
    _onboard(raw_client)
    r = raw_client.post(
        f"/api/chat/{alice_id}/suggestions", json={"conversation_id": conversation_id}
    )
    assert r.status_code == 403
