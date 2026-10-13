"""Per-chapter diagnostic: scoring table, seed isolation, and the API flow."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.diagnostic import (
    EXPERIENCE_LEVELS,
    Diagnostic,
    load_diagnostic,
    lookup_level,
    resolve_diagnostic,
    score,
)
from app.core.mapping import derive
from app.core.rules import RuleSet
from tests.conftest import make_profile

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"
EXAMPLE = CONTENT_DIR / "diagnostic.example.yaml"


@pytest.fixture(scope="module")
def diagnostic() -> Diagnostic:
    return load_diagnostic(EXAMPLE, "3")


def _raw() -> dict:
    return yaml.safe_load(EXAMPLE.read_text())


def test_every_scoring_table_row_returns_the_documented_level(diagnostic: Diagnostic) -> None:
    """The YAML is the documentation: every (experience, correct_count) cell
    must come back from lookup_level exactly as written."""
    documented = _raw()["scoring_table"]
    n_cells = 0
    for experience in EXPERIENCE_LEVELS:
        for count in range(len(diagnostic.items) + 1):
            assert lookup_level(diagnostic, count, experience) == documented[experience][count]
            n_cells += 1
    assert n_cells == len(EXPERIENCE_LEVELS) * (len(diagnostic.items) + 1)


def test_dont_know_scores_zero(diagnostic: Diagnostic) -> None:
    dont_know = [
        next(i for i, o in enumerate(item.options) if o.dont_know) for item in diagnostic.items
    ]
    count, level = score(diagnostic, dont_know, "low")
    assert count == 0
    assert level == lookup_level(diagnostic, 0, "low")


def test_all_correct_scores_full(diagnostic: Diagnostic) -> None:
    right = [next(i for i, o in enumerate(item.options) if o.correct) for item in diagnostic.items]
    assert score(diagnostic, right, "none")[0] == len(diagnostic.items)


def test_score_rejects_wrong_arity_and_bad_index(diagnostic: Diagnostic) -> None:
    with pytest.raises(ValueError):
        score(diagnostic, [0], "none")
    with pytest.raises(ValueError):
        score(diagnostic, [99] * len(diagnostic.items), "none")


def test_chapter_diagnostic_does_not_mutate_the_seed(
    diagnostic: Diagnostic, ruleset: RuleSet
) -> None:
    profile = make_profile(prior_knowledge_seed="low")
    before = profile.model_dump_json()
    _, chapter_level = score(diagnostic, [0] * len(diagnostic.items), profile.prior_knowledge_seed)
    derive(profile, ruleset, "high")
    assert profile.model_dump_json() == before
    assert profile.prior_knowledge_seed == "low"
    assert chapter_level in EXPERIENCE_LEVELS


def test_chapter_level_replaces_the_seed_for_the_mapping_call(ruleset: RuleSet) -> None:
    profile = make_profile(prior_knowledge_seed="none")
    seeded, seeded_attr = derive(profile, ruleset)
    chapter, chapter_attr = derive(profile, ruleset, "high")
    assert (seeded.explanation_depth, seeded_attr["explanation_depth"]) == (4, "pk_low")
    assert (chapter.explanation_depth, chapter_attr["explanation_depth"]) == (2, "pk_high")
    # ...and None means "no diagnostic ran": identical to the seed call.
    assert derive(profile, ruleset, None) == (seeded, seeded_attr)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r["items"].pop(), "items"),  # 2 items: below the minimum
        (lambda r: r["items"][0]["options"].pop(), "I don't know"),
        (lambda r: r["items"][0]["options"][1].update(correct=True), "exactly one correct"),
        (lambda r: r["scoring_table"]["low"].pop(2), "scoring_table lacks"),
    ],
)
def test_malformed_diagnostics_fail_at_load(tmp_path: Path, mutate, message: str) -> None:  # type: ignore[no-untyped-def]
    raw = _raw()
    mutate(raw)
    path = tmp_path / "diagnostic.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match=message):
        load_diagnostic(path, "3")


def test_subchapter_diagnostic_wins_over_chapter(diagnostic: Diagnostic) -> None:
    section = diagnostic.model_copy(update={"key": "3.1"})
    both = {"3": diagnostic, "3.1": section}
    assert resolve_diagnostic(both, "3", "3.1") is section
    assert resolve_diagnostic(both, "3", "3.2") is diagnostic
    assert resolve_diagnostic(both, "3", None) is diagnostic
    assert resolve_diagnostic({}, "3", None) is None


# --- API -------------------------------------------------------------------


@pytest.fixture
def with_diagnostic(client: TestClient, diagnostic: Diagnostic):  # type: ignore[no-untyped-def]
    """The running app with the example diagnostic installed for chapter 1."""
    state = client.app.state.itm  # type: ignore[attr-defined]
    state.diagnostics = {"1": diagnostic.model_copy(update={"key": "1"})}
    yield client
    state.diagnostics = {}


def _onboard(client: TestClient, seed: str = "low") -> str:
    r = client.post("/api/onboarding", json={"prior_knowledge_seed": seed})
    assert r.status_code == 200
    return str(r.json()["profile"]["learner_id"])


def _train(client: TestClient, learner_id: str) -> None:
    r = client.put(f"/api/mode/{learner_id}", json={"mode": "training", "chapter_number": "1"})
    assert r.status_code == 200


def _right_answers(diagnostic: Diagnostic) -> list[int]:
    return [next(i for i, o in enumerate(it.options) if o.correct) for it in diagnostic.items]


def test_status_hides_the_answer_key(with_diagnostic: TestClient) -> None:
    learner_id = _onboard(with_diagnostic)
    _train(with_diagnostic, learner_id)
    body = with_diagnostic.get(f"/api/diagnostic/{learner_id}").json()
    assert body["required"] is True and body["result"] is None
    assert "correct" not in str(body) and "dont_know" not in str(body)


def test_no_diagnostic_authored_means_not_required(client: TestClient) -> None:
    learner_id = _onboard(client)
    _train(client, learner_id)
    assert client.get(f"/api/diagnostic/{learner_id}").json() == {
        "required": False,
        "key": None,
        "items": [],
        "result": None,
    }


def test_instruction_is_gated_until_the_diagnostic_is_taken(
    with_diagnostic: TestClient, diagnostic: Diagnostic
) -> None:
    c = with_diagnostic
    learner_id = _onboard(c)
    _train(c, learner_id)
    assert c.post(f"/api/lesson/{learner_id}").status_code == 409
    assert c.post(f"/api/chat/{learner_id}", json={"message": "Hi"}).status_code == 409
    r = c.post(f"/api/diagnostic/{learner_id}", json={"answers": _right_answers(diagnostic)})
    assert r.status_code == 201
    # taken: the gate lifts (503 = got as far as the unconfigured LLM)
    assert c.post(f"/api/chat/{learner_id}", json={"message": "Hi"}).status_code != 409


def test_submit_stores_chapter_level_and_leaves_the_seed_alone(
    with_diagnostic: TestClient, diagnostic: Diagnostic
) -> None:
    c = with_diagnostic
    learner_id = _onboard(c, seed="none")
    _train(c, learner_id)
    r = c.post(f"/api/diagnostic/{learner_id}", json={"answers": _right_answers(diagnostic)})
    body = r.json()
    assert body["experience_seed"] == "none"
    assert body["correct_count"] == len(diagnostic.items)
    assert body["prior_knowledge"] == lookup_level(diagnostic, body["correct_count"], "none")
    config = c.get(f"/api/config/{learner_id}").json()
    assert config["profile"]["prior_knowledge_seed"] == "none"  # seed untouched
    assert config["chapter_diagnostic"]["prior_knowledge"] == body["prior_knowledge"]
    # re-onboarding-free retake is refused
    again = c.post(f"/api/diagnostic/{learner_id}", json={"answers": [0] * len(diagnostic.items)})
    assert again.status_code == 409


def test_other_chapter_still_uses_the_seed(
    with_diagnostic: TestClient, diagnostic: Diagnostic
) -> None:
    c = with_diagnostic
    learner_id = _onboard(c, seed="none")
    _train(c, learner_id)
    c.post(f"/api/diagnostic/{learner_id}", json={"answers": _right_answers(diagnostic)})
    c.put(f"/api/mode/{learner_id}", json={"mode": "training", "chapter_number": "2"})
    config = c.get(f"/api/config/{learner_id}").json()
    assert config["chapter_diagnostic"] is None
    assert config["attribution"]["explanation_depth"] == "pk_low"  # seed "none"


def test_summary_override_is_per_chapter_and_revertible(
    with_diagnostic: TestClient, diagnostic: Diagnostic
) -> None:
    c = with_diagnostic
    learner_id = _onboard(c)
    _train(c, learner_id)
    c.post(f"/api/diagnostic/{learner_id}", json={"answers": [0] * len(diagnostic.items)})
    derived = c.get(f"/api/diagnostic/{learner_id}").json()["result"]["derived"]

    r = c.put(f"/api/diagnostic/{learner_id}/override", json={"concreteness": 2})
    assert r.json()["effective"]["concreteness"] == 2
    assert r.json()["derived"] == derived  # the derived vector is never mutated
    # per-chapter: chapter 2 is unaffected
    c.put(f"/api/mode/{learner_id}", json={"mode": "training", "chapter_number": "2"})
    assert c.get(f"/api/config/{learner_id}").json()["effective"]["concreteness"] == 5
    c.put(f"/api/mode/{learner_id}", json={"mode": "training", "chapter_number": "1"})

    r = c.delete(f"/api/diagnostic/{learner_id}/override/concreteness")
    assert r.json()["effective"] == r.json()["derived"]


def test_invalid_answers_are_rejected(with_diagnostic: TestClient, diagnostic: Diagnostic) -> None:
    c = with_diagnostic
    learner_id = _onboard(c)
    _train(c, learner_id)
    assert c.post(f"/api/diagnostic/{learner_id}", json={"answers": [0]}).status_code == 422
    assert (
        c.post(
            f"/api/diagnostic/{learner_id}", json={"answers": [99] * len(diagnostic.items)}
        ).status_code
        == 422
    )


def test_instruction_routes_never_write_the_profile_or_diagnostics() -> None:
    """DR1, structurally: the routes that run instruction (chat, lesson) have no
    code path into the profile or diagnostic stores' write methods."""
    app_dir = Path(__file__).resolve().parents[1] / "app" / "api"
    for name in ("chat.py", "lesson.py", "conversations.py"):
        source = (app_dir / name).read_text()
        for write in (
            "chapter_diagnostics.create",
            "chapter_diagnostics.set_override",
            "profiles.create",
        ):
            assert write not in source, f"{name} calls {write}"
