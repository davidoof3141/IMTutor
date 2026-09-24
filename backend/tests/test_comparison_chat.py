import json

import pytest
from fastapi.testclient import TestClient

from app.llm.client import TutorResponse
from tests.conftest import SUPERUSER, login, make_learner


def _fake_stream(**kwargs: object):
    """Each call yields text derived from its own system prompt, so the two
    concurrent variants in a comparison turn are distinguishable without
    depending on which one happened to run first."""
    system_prompt = str(kwargs["system_prompt"])
    text = f"reply-{abs(hash(system_prompt)) % 100000}"
    yield text
    yield TutorResponse(text=text, model="test/model", prompt_tokens=1, completion_tokens=1)


def _stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.stream_turn", _fake_stream)


def _link_learner(raw_client: TestClient, username: str = "linked") -> str:
    """Creates a link-invited learner account, signs it in via its login
    link, onboards it, and leaves `raw_client` authenticated as it. Returns
    the new learner_id."""
    admin = login(raw_client, **SUPERUSER)
    r = raw_client.post(
        "/api/users/link",
        json={"username": username},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 201, r.text
    link_token = r.json()["link_token"]

    signed_in = raw_client.post("/api/auth/login-link", json={"token": link_token})
    assert signed_in.status_code == 200, signed_in.text
    raw_client.headers["Authorization"] = f"Bearer {signed_in.json()['token']}"

    onboarded = raw_client.post(
        "/api/onboarding",
        json={
            "role": "practitioner",
            "prior_experience": "low",
            "goal": "certification",
            "industry": "healthcare",
            "learner_type": "visuell",
        },
    )
    assert onboarded.status_code == 200, onboarded.text
    return str(onboarded.json()["profile"]["learner_id"])


def _read_ndjson(response) -> list[dict]:
    """Parses newline-delimited JSON from a streamed response -- chunk
    boundaries from `iter_text()` don't necessarily line up with newlines, so
    multiple events (or a split one) can land in a single chunk."""
    buffer = ""
    events = []
    for chunk in response.iter_text():
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip():
                events.append(json.loads(line))
    if buffer.strip():
        events.append(json.loads(buffer))
    return events


def test_compare_is_unavailable_for_password_accounts(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client)}"
    onboarded = raw_client.post(
        "/api/onboarding",
        json={
            "role": "practitioner",
            "prior_experience": "low",
            "goal": "certification",
            "industry": "healthcare",
            "learner_type": "visuell",
        },
    )
    learner_id = onboarded.json()["profile"]["learner_id"]

    r = raw_client.post(f"/api/chat/{learner_id}/compare", json={"message": "Hi"})
    assert r.status_code == 403


def test_compare_streams_both_variants_and_choose_persists_the_pick(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _link_learner(raw_client)

    with raw_client.stream(
        "POST", f"/api/chat/{learner_id}/compare", json={"message": "Was ist ein Marktrisiko?"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-ndjson")
        comparison_id = r.headers["x-comparison-id"]
        conversation_id = r.headers["x-conversation-id"]
        events = _read_ndjson(r)

    texts: dict[str, str] = {}
    for label in ("a", "b"):
        deltas = "".join(e["delta"] for e in events if e["variant"] == label and "delta" in e)
        assert any(e["variant"] == label and e.get("done") for e in events)
        texts[label] = deltas
    # The comparison is a live A/B: the two variants differ (different system
    # prompts -- personalized vs. the rule set's plain defaults).
    assert texts["a"] != texts["b"]

    # Nothing is in the conversation yet -- the learner hasn't picked.
    assert raw_client.get(f"/api/conversations/{learner_id}").json()[0]["message_count"] == 0

    chosen = raw_client.post(
        f"/api/chat/{learner_id}/compare/{comparison_id}/choose",
        json={"variant": "a", "reasons": ["detail", "tone"]},
    )
    assert chosen.status_code == 200
    assert chosen.json()["conversation_id"] == conversation_id

    messages = raw_client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()
    assert [(m["role"], m["text"]) for m in messages] == [
        ("learner", "Was ist ein Marktrisiko?"),
        ("tutor", texts["a"]),
    ]

    log = raw_client.get(f"/api/export/{learner_id}").json()
    assert len(log) == 1
    assert log[0]["completion"] == texts["a"]


def test_choose_cannot_be_repeated(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _link_learner(raw_client)

    with raw_client.stream(
        "POST", f"/api/chat/{learner_id}/compare", json={"message": "Hi"}
    ) as r:
        comparison_id = r.headers["x-comparison-id"]
        list(r.iter_text())

    first = raw_client.post(
        f"/api/chat/{learner_id}/compare/{comparison_id}/choose",
        json={"variant": "b", "reasons": ["clarity"]},
    )
    assert first.status_code == 200

    second = raw_client.post(
        f"/api/chat/{learner_id}/compare/{comparison_id}/choose",
        json={"variant": "a", "reasons": ["clarity"]},
    )
    assert second.status_code == 404


def test_choose_requires_free_text_when_other_reason_is_selected(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _link_learner(raw_client)

    with raw_client.stream(
        "POST", f"/api/chat/{learner_id}/compare", json={"message": "Hi"}
    ) as r:
        comparison_id = r.headers["x-comparison-id"]
        list(r.iter_text())

    missing_text = raw_client.post(
        f"/api/chat/{learner_id}/compare/{comparison_id}/choose",
        json={"variant": "a", "reasons": ["other"]},
    )
    assert missing_text.status_code == 400

    with_text = raw_client.post(
        f"/api/chat/{learner_id}/compare/{comparison_id}/choose",
        json={"variant": "a", "reasons": ["other"], "other_reason": "Es hat einfach gepasst."},
    )
    assert with_text.status_code == 200


def test_compare_requires_at_least_one_reason(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _link_learner(raw_client)

    with raw_client.stream(
        "POST", f"/api/chat/{learner_id}/compare", json={"message": "Hi"}
    ) as r:
        comparison_id = r.headers["x-comparison-id"]
        list(r.iter_text())

    r = raw_client.post(
        f"/api/chat/{learner_id}/compare/{comparison_id}/choose",
        json={"variant": "a", "reasons": []},
    )
    assert r.status_code == 422


def test_another_learners_comparison_is_not_reachable(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    alice_id = _link_learner(raw_client, "alice-linked")
    with raw_client.stream(
        "POST", f"/api/chat/{alice_id}/compare", json={"message": "Hi"}
    ) as r:
        comparison_id = r.headers["x-comparison-id"]
        list(r.iter_text())

    bob_id = _link_learner(raw_client, "bob-linked")
    r = raw_client.post(
        f"/api/chat/{bob_id}/compare/{comparison_id}/choose",
        json={"variant": "a", "reasons": ["detail"]},
    )
    assert r.status_code == 404
