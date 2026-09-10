import pytest
from fastapi.testclient import TestClient

from app.rag.chapter_intros import ChapterIntro
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


def _set_training_mode(
    client: TestClient,
    learner_id: str,
    chapter_number: str = "1",
    section_number: str | None = None,
) -> None:
    r = client.put(
        f"/api/mode/{learner_id}",
        json={
            "mode": "training",
            "chapter_number": chapter_number,
            "section_number": section_number,
        },
    )
    assert r.status_code == 200, r.text


def _stub_manifest(monkeypatch: pytest.MonkeyPatch, entries: dict[str, ChapterIntro]) -> None:
    monkeypatch.setattr("app.api.chapter_intro.load_chapter_intros", lambda: entries)


def test_chapter_intro_requires_training_mode_with_chapter(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    assert client.get(f"/api/chapter-intro/{learner_id}").status_code == 400


def test_chapter_intro_returns_the_pre_generated_text_and_starters_for_a_whole_chapter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_manifest(
        monkeypatch,
        {
            "1": ChapterIntro(
                text="Willkommen im Kapitel!",
                starters=("Was ist Informationsmanagement?", "Warum ist das wichtig?"),
            )
        },
    )
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id, chapter_number="1")

    r = client.get(f"/api/chapter-intro/{learner_id}")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "text": "Willkommen im Kapitel!",
        "starters": ["Was ist Informationsmanagement?", "Warum ist das wichtig?"],
    }


def test_chapter_intro_starters_are_capped_at_three(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_manifest(
        monkeypatch,
        {"1": ChapterIntro(text="x", starters=tuple(f"Frage {n}?" for n in range(5)))},
    )
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id, chapter_number="1")

    starters = client.get(f"/api/chapter-intro/{learner_id}").json()["starters"]
    assert starters == ["Frage 0?", "Frage 1?", "Frage 2?"]


def test_chapter_intro_without_starters_returns_an_empty_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_manifest(monkeypatch, {"1": ChapterIntro(text="Nur Text.")})
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id, chapter_number="1")

    r = client.get(f"/api/chapter-intro/{learner_id}")
    assert r.json() == {"text": "Nur Text.", "starters": []}


def test_chapter_intro_uses_the_chapter_colon_section_key_for_a_section(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    r = client.get("/api/curriculum")
    chapter = next(c for c in r.json()["chapters"] if c["sections"])
    section = chapter["sections"][0]
    _stub_manifest(
        monkeypatch,
        {f"{chapter['number']}:{section['number']}": ChapterIntro(text="Willkommen im Abschnitt!")},
    )
    _set_training_mode(
        client, learner_id, chapter_number=chapter["number"], section_number=section["number"]
    )

    r = client.get(f"/api/chapter-intro/{learner_id}")
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "Willkommen im Abschnitt!", "starters": []}


def test_chapter_intro_missing_from_manifest_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_manifest(monkeypatch, {})
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id, chapter_number="1")

    assert client.get(f"/api/chapter-intro/{learner_id}").status_code == 404


def test_chapter_intro_is_a_static_lookup_no_conversation_or_turn_log_created(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_manifest(monkeypatch, {"1": ChapterIntro(text="Willkommen im Kapitel!")})
    learner_id = _onboard(client)["profile"]["learner_id"]
    _set_training_mode(client, learner_id, chapter_number="1")

    client.get(f"/api/chapter-intro/{learner_id}")

    assert client.get(f"/api/conversations/{learner_id}").json() == []
    assert client.get(f"/api/export/{learner_id}").json() == []


def test_chapter_intro_requires_ownership(raw_client: TestClient) -> None:
    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'alice', 'password1')}"
    alice_id = _onboard(raw_client)["profile"]["learner_id"]
    _set_training_mode(raw_client, alice_id)

    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'bob', 'password1')}"
    _onboard(raw_client)
    assert raw_client.get(f"/api/chapter-intro/{alice_id}").status_code == 403
