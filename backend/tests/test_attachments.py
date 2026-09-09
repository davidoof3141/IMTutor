import base64
import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.llm.client import TutorResponse
from tests.conftest import make_learner

# A minimal valid 1x1 transparent PNG.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _onboard(client: TestClient) -> dict:
    response = client.post(
        "/api/onboarding",
        json={
            "role": "practitioner",
            "prior_experience": "low",
            "goal": "certification",
            "study_time": "under_2h",
            "learner_type": "visuell",
        },
    )
    assert response.status_code == 200
    return response.json()


def _stub_llm(monkeypatch: pytest.MonkeyPatch, seen: list | None = None):
    def fake_stream(**kwargs: object):
        if seen is not None:
            seen.append(kwargs)
        yield "ok"
        yield TutorResponse(text="ok", model="test/model", prompt_tokens=1, completion_tokens=1)

    monkeypatch.setattr("app.api.chat.assert_configured", lambda: None)
    monkeypatch.setattr("app.api.chat.stream_turn", fake_stream)


def test_upload_returns_metadata_without_bytes_or_extracted_text(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]

    r = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "filename", "mime_type", "kind", "size_bytes"}
    assert body["filename"] == "notes.txt"
    assert body["kind"] == "document"
    assert body["size_bytes"] == len(b"hello world")

    r = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("pixel.png", _PNG_BYTES, "image/png")},
    )
    assert r.status_code == 201
    assert r.json()["kind"] == "image"

    r = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 201
    assert r.json()["kind"] == "document"


def test_upload_rejects_unsupported_mime_type(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    r = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
    )
    assert r.status_code == 415


def test_upload_rejects_oversized_file(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    oversized = b"a" * (8 * 1024 * 1024 + 1)
    r = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("big.txt", oversized, "text/plain")},
    )
    assert r.status_code == 413


def test_upload_with_unknown_conversation_id_404s(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    r = client.post(
        f"/api/attachments/{learner_id}",
        data={"conversation_id": "does-not-exist"},
        files={"file": ("notes.txt", b"hi", "text/plain")},
    )
    assert r.status_code == 404


def test_attachment_download_returns_bytes_and_content_type(client: TestClient) -> None:
    learner_id = _onboard(client)["profile"]["learner_id"]
    upload = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("pixel.png", _PNG_BYTES, "image/png")},
    ).json()

    r = client.get(f"/api/attachments/{learner_id}/{upload['id']}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == _PNG_BYTES


def test_attachment_download_of_another_learners_attachment_404s(
    raw_client: TestClient,
) -> None:
    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'alice', 'password1')}"
    alice_id = _onboard(raw_client)["profile"]["learner_id"]
    upload = raw_client.post(
        f"/api/attachments/{alice_id}",
        files={"file": ("notes.txt", b"secret", "text/plain")},
    ).json()

    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'bob', 'password1')}"
    bob_id = _onboard(raw_client)["profile"]["learner_id"]
    r = raw_client.get(f"/api/attachments/{bob_id}/{upload['id']}")
    assert r.status_code == 404


def test_chat_with_attachment_ids_passes_documents_and_images_to_stream_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list = []
    _stub_llm(monkeypatch, seen)
    learner_id = _onboard(client)["profile"]["learner_id"]

    doc = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    ).json()
    image = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("pixel.png", _PNG_BYTES, "image/png")},
    ).json()

    client.post(
        f"/api/chat/{learner_id}",
        json={"message": "Was siehst du?", "attachment_ids": [doc["id"], image["id"]]},
    )

    assert seen[0]["document_texts"] == [("notes.txt", "hello world")]
    assert len(seen[0]["image_data_urls"]) == 1
    assert seen[0]["image_data_urls"][0].startswith("data:image/png;base64,")


def test_chat_ignores_attachment_ids_belonging_to_another_learner(
    raw_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list = []
    _stub_llm(monkeypatch, seen)

    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'alice', 'password1')}"
    alice_id = _onboard(raw_client)["profile"]["learner_id"]
    foreign_attachment = raw_client.post(
        f"/api/attachments/{alice_id}",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    ).json()

    raw_client.headers["Authorization"] = f"Bearer {make_learner(raw_client, 'bob', 'password1')}"
    bob_id = _onboard(raw_client)["profile"]["learner_id"]

    raw_client.post(
        f"/api/chat/{bob_id}",
        json={"message": "Hi", "attachment_ids": [foreign_attachment["id"]]},
    )

    assert seen[0]["document_texts"] == []
    assert seen[0]["image_data_urls"] == []


def test_chat_links_attachments_to_the_learner_message_and_history_replay_includes_them(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]

    doc = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    ).json()

    r = client.post(
        f"/api/chat/{learner_id}",
        json={"message": "Was steht hier?", "attachment_ids": [doc["id"]]},
    )
    conversation_id = r.headers["x-conversation-id"]

    messages = client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()
    learner_message = next(m for m in messages if m["role"] == "learner")
    assert [a["id"] for a in learner_message["attachments"]] == [doc["id"]]
    tutor_message = next(m for m in messages if m["role"] == "tutor")
    assert tutor_message["attachments"] == []


def test_upload_before_conversation_exists_is_linked_on_first_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch)
    learner_id = _onboard(client)["profile"]["learner_id"]

    # No conversation_id given -- this is a fresh, unsaved thread.
    doc = client.post(
        f"/api/attachments/{learner_id}",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    ).json()

    r = client.post(
        f"/api/chat/{learner_id}",
        json={"message": "Hi", "attachment_ids": [doc["id"]]},
    )
    conversation_id = r.headers["x-conversation-id"]

    messages = client.get(f"/api/conversations/{learner_id}/{conversation_id}/messages").json()
    learner_message = next(m for m in messages if m["role"] == "learner")
    assert [a["id"] for a in learner_message["attachments"]] == [doc["id"]]
