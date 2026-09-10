import pytest
from fastapi.testclient import TestClient

from app.llm.client import TutorResponse


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
    assert response.status_code == 200
    return response.json()


def test_onboarding_returns_derived_vector_and_attribution(client: TestClient) -> None:
    body = _onboard(client)
    assert body["profile"]["role"] == "practitioner"
    assert body["derived"]["explanation_depth"] == 4  # exp_low rule
    assert body["attribution"]["explanation_depth"] == "exp_low"
    assert body["derived"]["register"] == "informal"
    assert body["attribution"]["register"] == "role_practitioner"
    assert body["derived"]["assessment_frequency"] == "every_topic"
    assert body["attribution"]["assessment_frequency"] == "goal_certification"
    assert body["derived"]["example_domain"] == "healthcare"
    assert body["attribution"]["example_domain"] == "industry_healthcare"


def test_chat_streams_the_reply_and_logs_the_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_stream(**_: object):
        yield "Hallo "
        yield "Welt"
        yield TutorResponse(text="Hallo Welt", model="test/model", prompt_tokens=3, completion_tokens=2)

    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.stream_turn", fake_stream)

    learner_id = _onboard(client)["profile"]["learner_id"]

    with client.stream("POST", f"/api/chat/{learner_id}", json={"message": "Hi"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        body = "".join(response.iter_text())
    assert body == "Hallo Welt"

    log = client.get(f"/api/export/{learner_id}").json()
    assert len(log) == 1
    assert log[0]["completion"] == "Hallo Welt"
    assert log[0]["model"] == "test/model"
    assert log[0]["completion_tokens"] == 2


def test_chat_requires_auth(raw_client: TestClient) -> None:
    assert raw_client.post("/api/chat/whoever", json={"message": "Hi"}).status_code == 401


def _stub_llm(monkeypatch: pytest.MonkeyPatch, seen: list | None = None):
    """Monkeypatches the chat LLM call; records the kwargs it was given."""

    def fake_stream(**kwargs: object):
        if seen is not None:
            seen.append(kwargs)
        yield "ok"
        yield TutorResponse(text="ok", model="test/model", prompt_tokens=1, completion_tokens=1)

    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.stream_turn", fake_stream)


def test_chat_creates_a_conversation_and_persists_both_messages(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]

    with client.stream("POST", f"/api/chat/{learner_id}", json={"message": "Was ist Marktrisiko?"}) as r:
        assert r.status_code == 200
        "".join(r.iter_text())
        conversation_id = r.headers["x-conversation-id"]

    conversations = client.get(f"/api/conversations/{learner_id}").json()
    assert len(conversations) == 1
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == "Was ist Marktrisiko?"
    assert conversations[0]["message_count"] == 2

    messages = client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()
    assert [(m["role"], m["text"]) for m in messages] == [
        ("learner", "Was ist Marktrisiko?"),
        ("tutor", "ok"),
    ]


def test_chat_replays_prior_turns_when_resuming_a_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list = []
    _stub_llm(monkeypatch, seen)
    learner_id = _onboard(client)["profile"]["learner_id"]

    first = client.post(f"/api/chat/{learner_id}", json={"message": "Erste Frage"})
    conversation_id = first.headers["x-conversation-id"]

    client.post(
        f"/api/chat/{learner_id}",
        json={"message": "Zweite Frage", "conversation_id": conversation_id},
    )

    # The second call must have been given the first turn as history.
    assert seen[0]["history"] == []
    assert seen[1]["history"] == [
        {"role": "user", "content": "Erste Frage"},
        {"role": "assistant", "content": "ok"},
    ]


def test_chat_with_unknown_conversation_id_starts_a_fresh_thread(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]

    r = client.post(
        f"/api/chat/{learner_id}",
        json={"message": "Hi", "conversation_id": "does-not-exist"},
    )
    assert r.headers["x-conversation-id"] != "does-not-exist"
    assert len(client.get(f"/api/conversations/{learner_id}").json()) == 1


def test_conversation_messages_of_another_learner_are_hidden(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import make_learner

    _stub_llm(monkeypatch)
    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'alice', 'password1')}"
    alice_id = _onboard(raw_client)["profile"]["learner_id"]
    conv_id = raw_client.post(f"/api/chat/{alice_id}", json={"message": "Hi"}).headers[
        "x-conversation-id"
    ]

    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'bob', 'password1')}"
    bob_id = _onboard(raw_client)["profile"]["learner_id"]
    assert raw_client.get(f"/api/conversations/{bob_id}/{conv_id}/messages").status_code == 404


def test_get_config_reflects_overrides(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]

    response = client.get(f"/api/config/{learner_id}")
    assert response.status_code == 200
    config = response.json()
    assert config["override"] == {}
    assert config["effective"] == config["derived"]

    response = client.put(f"/api/config/{learner_id}/override", json={"concreteness": 1})
    assert response.status_code == 200
    config = response.json()
    assert config["override"] == {"concreteness": 1}
    assert config["effective"]["concreteness"] == 1
    assert config["derived"]["concreteness"] == 4  # override must not mutate the derived vector

    response = client.delete(f"/api/config/{learner_id}/override/concreteness")
    assert response.status_code == 200
    assert response.json()["override"] == {}


def test_get_config_unknown_learner_404s(client: TestClient) -> None:
    response = client.get("/api/config/does-not-exist")
    assert response.status_code == 404


def test_get_rules_returns_ruleset_and_catalogue(client: TestClient) -> None:
    response = client.get("/api/rules", params={"version": "v1"})
    assert response.status_code == 200
    body = response.json()
    assert body["ruleset"]["version"] == "v1"
    assert body["catalogue"]["version"] == "v1"


def test_export_before_any_chat_is_empty(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    response = client.get(f"/api/export/{learner_id}")
    assert response.status_code == 200
    assert response.json() == []


def test_get_curriculum_returns_chapters_extracted_from_the_book(client: TestClient) -> None:
    response = client.get("/api/curriculum")
    assert response.status_code == 200
    chapters = response.json()["chapters"]
    assert len(chapters) == 11
    assert chapters[0]["number"] == "1"
    assert chapters[0]["title"] == "Einleitung"
    assert len(chapters[0]["sections"]) > 0


def test_mode_defaults_to_exploration(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    response = client.get(f"/api/mode/{learner_id}")
    assert response.status_code == 200
    assert response.json() == {"mode": "exploration", "chapter_number": None, "section_number": None}


def test_mode_can_be_set_to_training_with_a_chapter_and_persists(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    response = client.put(f"/api/mode/{learner_id}", json={"mode": "training", "chapter_number": "5"})
    assert response.status_code == 200
    assert response.json() == {"mode": "training", "chapter_number": "5", "section_number": None}

    response = client.get(f"/api/mode/{learner_id}")
    assert response.json()["chapter_number"] == "5"


def test_mode_rejects_unknown_chapter(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    response = client.put(f"/api/mode/{learner_id}", json={"mode": "training", "chapter_number": "999"})
    assert response.status_code == 400


def test_mode_rejects_unknown_learner(client: TestClient) -> None:
    response = client.get("/api/mode/does-not-exist")
    assert response.status_code == 404
