"""Link-invited accounts only get chapter 4, sections 4.1-4.3, in training mode."""

import pytest
from fastapi.testclient import TestClient

from tests.test_comparison_chat import _link_learner


def _put(client: TestClient, learner_id: str, **body: str) -> int:
    return client.put(f"/api/mode/{learner_id}", json={"mode": "training", **body}).status_code


@pytest.mark.parametrize("section", [None, "4.1", "4.2", "4.3"])
def test_link_user_can_open_chapter_4_and_its_first_three_sections(
    raw_client: TestClient, section: str | None
) -> None:
    learner_id = _link_learner(raw_client)
    body = {"chapter_number": "4"} | ({"section_number": section} if section else {})
    assert _put(raw_client, learner_id, **body) == 200


@pytest.mark.parametrize("chapter", ["1", "2", "3"])
def test_link_user_cannot_open_other_chapters(raw_client: TestClient, chapter: str) -> None:
    learner_id = _link_learner(raw_client)
    assert _put(raw_client, learner_id, chapter_number=chapter) == 403


def test_link_user_cannot_open_a_section_outside_the_slice(raw_client: TestClient) -> None:
    learner_id = _link_learner(raw_client)
    assert _put(raw_client, learner_id, chapter_number="4", section_number="4.4") in (400, 403)
    assert _put(raw_client, learner_id, chapter_number="4", section_number="3.1") in (400, 403)


def test_regular_learner_is_not_restricted(client: TestClient) -> None:
    learner_id = client.post("/api/onboarding", json={}).json()["profile"]["learner_id"]
    assert _put(client, learner_id, chapter_number="3") == 200
