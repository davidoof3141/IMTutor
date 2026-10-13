"""Rapid diagnostics (Kalyuga & Sweller 2004): scoring table, item-schema
validator, generator idempotency, API gating, startup validation, staleness."""

import copy
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.diagnostic import (
    DONT_KNOW_TEXT,
    LEVELS,
    SEEDS,
    Diagnostic,
    DiagnosticFileError,
    ScoringTable,
    load_diagnostic,
    load_diagnostics,
    load_scoring_table,
    lookup_level,
    parse_diagnostic,
    score,
    stale_chapters,
)
from app.core.mapping import derive
from app.core.rules import RuleSet
from tests.conftest import SUPERUSER, login, make_profile

DIAGNOSTICS_DIR = Path(__file__).resolve().parents[1] / "content" / "diagnostics"
SCORING_PATH = DIAGNOSTICS_DIR / "scoring_table.yaml"


def valid_raw(chapter_id: str = "1", source_hash: str = "h1") -> dict:  # type: ignore[type-arg]
    def item(n: int, level: str) -> dict:  # type: ignore[type-arg]
        return {
            "id": f"q{n}",
            "level": level,
            "stem": f"Frage {n}?",
            "options": [
                {"text": f"richtig {n}", "correct": True},
                {"text": f"falsch A {n}"},
                {"text": f"falsch B {n}"},
                {"text": DONT_KNOW_TEXT},
            ],
        }

    return {
        "chapter_id": chapter_id,
        "course_id": "informationsmanagement",
        "source_hash": source_hash,
        "generator_model": "test-model",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "items": [item(i + 1, level) for i, level in enumerate(LEVELS)],
    }


@pytest.fixture(scope="module")
def table() -> ScoringTable:
    return load_scoring_table(SCORING_PATH)


@pytest.fixture
def diagnostic() -> Diagnostic:
    return parse_diagnostic(valid_raw())


# --- scoring table -----------------------------------------------------------

# correct -> (level for seed none/low, level for seed moderate/high), as specified.
DOCUMENTED = {
    0: ("none", "low"),
    1: ("low", "low"),
    2: ("low", "moderate"),
    3: ("moderate", "moderate"),
    4: ("moderate", "high"),
}


@pytest.mark.parametrize("correct", sorted(DOCUMENTED))
@pytest.mark.parametrize("seed", SEEDS)
def test_scoring_table_lookup_returns_the_documented_level(
    table: ScoringTable, correct: int, seed: str
) -> None:
    low_seed, high_seed = DOCUMENTED[correct]
    expected = low_seed if seed in ("none", "low") else high_seed
    assert lookup_level(table, correct, seed) == expected  # type: ignore[arg-type]


def test_scoring_table_must_resolve_every_pair(tmp_path: Path) -> None:
    raw = yaml.safe_load(SCORING_PATH.read_text())
    raw["table"].pop()  # (4, moderate/high) no longer resolves
    path = tmp_path / "scoring_table.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(DiagnosticFileError, match="does not resolve") as exc:
        load_scoring_table(path)
    assert str(path) in str(exc.value)


def test_scoring_table_rejects_a_pair_listed_twice(tmp_path: Path) -> None:
    raw = yaml.safe_load(SCORING_PATH.read_text())
    raw["table"].append({"correct": 0, "seed": ["none"], "level": "low"})
    path = tmp_path / "scoring_table.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(DiagnosticFileError, match="listed twice"):
        load_scoring_table(path)


def test_dont_know_scores_zero(diagnostic: Diagnostic, table: ScoringTable) -> None:
    dont_know = [next(i for i, o in enumerate(it.options) if o.dont_know) for it in diagnostic.items]
    count, level = score(diagnostic, dont_know, "low", table)
    assert (count, level) == (0, "none")


def test_all_correct_scores_full(diagnostic: Diagnostic, table: ScoringTable) -> None:
    right = [next(i for i, o in enumerate(it.options) if o.correct) for it in diagnostic.items]
    assert score(diagnostic, right, "high", table) == (4, "high")


def test_score_rejects_wrong_arity_and_bad_index(
    diagnostic: Diagnostic, table: ScoringTable
) -> None:
    with pytest.raises(ValueError):
        score(diagnostic, [0], "none", table)
    with pytest.raises(ValueError):
        score(diagnostic, [99] * 4, "none", table)


def test_chapter_level_does_not_mutate_the_seed(
    diagnostic: Diagnostic, table: ScoringTable, ruleset: RuleSet
) -> None:
    profile = make_profile(prior_knowledge_seed="low")
    before = profile.model_dump_json()
    score(diagnostic, [0] * 4, profile.prior_knowledge_seed, table)
    derive(profile, ruleset, "high")
    assert profile.model_dump_json() == before


def test_chapter_level_replaces_the_seed_for_the_mapping_call(ruleset: RuleSet) -> None:
    profile = make_profile(prior_knowledge_seed="none")
    seeded, seeded_attr = derive(profile, ruleset)
    chapter, chapter_attr = derive(profile, ruleset, "high")
    assert (seeded.explanation_depth, seeded_attr["explanation_depth"]) == (4, "pk_low")
    assert (chapter.explanation_depth, chapter_attr["explanation_depth"]) == (2, "pk_high")
    assert derive(profile, ruleset, None) == (seeded, seeded_attr)


# --- item-schema validator -----------------------------------------------------


def _mutated(mutate) -> dict:  # type: ignore[no-untyped-def,type-arg]
    raw = copy.deepcopy(valid_raw())
    mutate(raw)
    return raw


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r["items"].pop(), "one per level"),  # 3 items
        (lambda r: r["items"].reverse(), "one per level"),  # wrong order
        (lambda r: r["items"][1].update(level="recognition"), "one per level"),
        (lambda r: r["items"][0]["options"].pop(0), "exactly 4 options"),
        (lambda r: r["items"][0]["options"].append({"text": "extra"}), "exactly 4 options"),
        (lambda r: r["items"][0]["options"][3].update(text="Weiß nicht"), "I don't know"),
        (lambda r: r["items"][0]["options"][1].update(correct=True), "exactly one correct"),
        (lambda r: r["items"][0]["options"][0].pop("correct"), "exactly one correct"),
        (lambda r: r["items"][0]["options"][3].update(correct=True), "exactly one correct"),
        (lambda r: r["items"][0]["options"][1].update(text="richtig 1"), "not distinct"),
        (lambda r: r["items"][0].update(stem="  "), "empty stem"),
        (lambda r: r["items"][0]["options"][1].update(text=""), "empty option"),
        (lambda r: r.pop("source_hash"), "source_hash"),
    ],
)
def test_item_schema_validator_rejects(mutate, message: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match=message):
        parse_diagnostic(_mutated(mutate))


def test_valid_diagnostic_passes(diagnostic: Diagnostic) -> None:
    assert [i.level for i in diagnostic.items] == list(LEVELS)


def test_load_names_the_failing_file(tmp_path: Path) -> None:
    course = tmp_path / "informationsmanagement"
    course.mkdir()
    raw = valid_raw()
    raw["items"].pop()
    (course / "1.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(DiagnosticFileError) as exc:
        load_diagnostics(tmp_path)
    assert str(course / "1.yaml") in str(exc.value)


def test_file_name_must_match_chapter_id(tmp_path: Path) -> None:
    course = tmp_path / "informationsmanagement"
    course.mkdir()
    (course / "2.yaml").write_text(yaml.safe_dump(valid_raw(chapter_id="1")))
    with pytest.raises(DiagnosticFileError, match="does not match the file name"):
        load_diagnostic(course / "2.yaml")


def test_shipped_files_are_valid() -> None:
    assert load_scoring_table(SCORING_PATH)
    shipped = load_diagnostics(DIAGNOSTICS_DIR)
    assert "4" in shipped  # the worked example


def test_stale_chapters_compares_hashes(diagnostic: Diagnostic) -> None:
    diagnostics = {"1": diagnostic}
    assert stale_chapters(diagnostics, {"1": "h1"}) == []
    assert stale_chapters(diagnostics, {"1": "other"}) == ["1"]
    assert stale_chapters(diagnostics, {}) == []  # not in the database: not reported


# --- generator -------------------------------------------------------------------


def _load_generator():  # type: ignore[no-untyped-def]
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_diagnostics", Path(__file__).resolve().parents[1] / "scripts" / "generate_diagnostics.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_generator()


def _chapter(number: str = "1"):  # type: ignore[no-untyped-def]
    from app.rag.toc import Chapter

    return Chapter(number=number, title="Titel", page_start=1, page_end=2, sections=[])


def _model_json() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "level": level,
                    "stem": f"Frage {i}?",
                    "options": [
                        {"text": f"richtig {i}", "correct": True},
                        {"text": f"falsch A {i}"},
                        {"text": f"falsch B {i}"},
                    ],
                }
                for i, level in enumerate(LEVELS, start=1)
            ]
        }
    )


class FakeLLM:
    def __init__(self, replies: list[str] | None = None) -> None:
        self.calls = 0
        self._replies = replies

    def __call__(self, system_prompt: str, text: str, model: str) -> tuple[str, str]:
        self.calls += 1
        reply = self._replies[min(self.calls - 1, len(self._replies) - 1)] if self._replies else _model_json()
        return reply, "fake-model"


def _run(out_dir: Path, text: str, llm: FakeLLM, **kw):  # type: ignore[no-untyped-def]
    return GENERATOR.process_chapter(
        chapter=_chapter(), text=text, out_dir=out_dir, course_id="informationsmanagement",
        model="m", llm=llm, **kw,
    )


def test_generator_is_idempotent_when_source_hash_is_unchanged(tmp_path: Path) -> None:
    llm = FakeLLM()
    assert _run(tmp_path, "Kapiteltext", llm) == "written"
    path = tmp_path / "informationsmanagement" / "1.yaml"
    first = path.read_text()
    assert llm.calls == 1

    assert _run(tmp_path, "Kapiteltext", llm) == "skipped"
    assert llm.calls == 1  # no second model call
    assert path.read_text() == first  # byte-identical: not rewritten, not re-timestamped


def test_generator_regenerates_when_the_text_changes_or_forced(tmp_path: Path) -> None:
    llm = FakeLLM()
    _run(tmp_path, "Kapiteltext", llm)
    assert _run(tmp_path, "Kapiteltext, geändert", llm) == "written"
    assert llm.calls == 2
    assert _run(tmp_path, "Kapiteltext, geändert", llm, force=True) == "written"
    assert llm.calls == 3


def test_generated_file_is_valid_and_appends_dont_know_last(tmp_path: Path) -> None:
    _run(tmp_path, "Kapiteltext", FakeLLM())
    generated = load_diagnostic(tmp_path / "informationsmanagement" / "1.yaml")
    assert generated.generator_model == "fake-model"
    for item in generated.items:
        assert len(item.options) == 4
        assert item.options[-1].text == DONT_KNOW_TEXT
        assert sum(o.correct for o in item.options) == 1


def test_generator_retries_invalid_output_then_succeeds(tmp_path: Path) -> None:
    llm = FakeLLM(["kein json", _model_json()])
    assert _run(tmp_path, "Kapiteltext", llm) == "written"
    assert llm.calls == 2


def test_generator_gives_up_and_writes_nothing_on_persistent_invalid_output(tmp_path: Path) -> None:
    llm = FakeLLM(['{"items": []}'])
    with pytest.raises(GENERATOR.GenerationError):
        _run(tmp_path, "Kapiteltext", llm)
    assert not (tmp_path / "informationsmanagement" / "1.yaml").exists()


def test_generator_refuses_an_over_long_chapter_instead_of_truncating(tmp_path: Path) -> None:
    llm = FakeLLM()
    with pytest.raises(GENERATOR.GenerationError, match="not truncating"):
        _run(tmp_path, "x" * 50, llm, max_chars=10)
    assert llm.calls == 0


def test_generator_ignores_empty_chapters(tmp_path: Path) -> None:
    llm = FakeLLM()
    assert _run(tmp_path, "", llm) == "empty"
    assert llm.calls == 0


def test_option_order_is_reproducible() -> None:
    raw = json.loads(_model_json())["items"]
    assert GENERATOR.build_items(raw, chapter_id="4") == GENERATOR.build_items(raw, chapter_id="4")


def test_generator_stale_listing(tmp_path: Path, db_conn) -> None:  # type: ignore[no-untyped-def]
    from app.rag.chapter_text import chapter_text, source_hash
    from app.store.book_chunks import BookChunkRepository

    chapter = _chapter()
    BookChunkRepository(db_conn).replace_all([("b-p1-0", "Text A", 1, [0.0] * 1536)])
    kwargs = {"curriculum": [chapter], "conn": db_conn, "out_dir": tmp_path,
              "course_id": "informationsmanagement"}
    assert GENERATOR.list_stale(**kwargs) == [("1", "missing")]
    _run(tmp_path, chapter_text(db_conn, chapter), FakeLLM())
    assert GENERATOR.list_stale(**kwargs) == []
    BookChunkRepository(db_conn).replace_all([("b-p1-0", "Text B", 1, [0.0] * 1536)])
    assert GENERATOR.list_stale(**kwargs) == [("1", "stale")]
    assert source_hash("Text B") != source_hash("Text A")


# --- API: gating, summary, overrides ---------------------------------------------


@pytest.fixture
def with_diagnostic(client: TestClient, diagnostic: Diagnostic):  # type: ignore[no-untyped-def]
    """The running app with a diagnostic installed for chapter 1 only."""
    state = client.app.state.itm  # type: ignore[attr-defined]
    state.diagnostics = {"1": diagnostic}
    yield client
    state.diagnostics = {}


def _onboard(client: TestClient, seed: str = "low") -> str:
    r = client.post("/api/onboarding", json={"prior_knowledge_seed": seed})
    assert r.status_code == 200
    return str(r.json()["profile"]["learner_id"])


def _train(client: TestClient, learner_id: str, chapter: str = "1") -> None:
    r = client.put(f"/api/mode/{learner_id}", json={"mode": "training", "chapter_number": chapter})
    assert r.status_code == 200


RIGHT = [0, 0, 0, 0]  # valid_raw() puts the correct option first


def test_status_hides_the_answer_key_and_localizes_dont_know(with_diagnostic: TestClient) -> None:
    learner_id = _onboard(with_diagnostic)
    _train(with_diagnostic, learner_id)
    body = with_diagnostic.get(f"/api/diagnostic/{learner_id}").json()
    assert body["required"] is True and body["result"] is None
    assert "correct" not in str(body)
    assert DONT_KNOW_TEXT not in str(body)
    assert body["items"][0]["options"][-1]["text"] == "Ich weiß es nicht"


def test_gating_409_until_a_diagnostic_file_exists_and_the_learner_took_it(
    client: TestClient, diagnostic: Diagnostic
) -> None:
    state = client.app.state.itm  # type: ignore[attr-defined]
    learner_id = _onboard(client)
    _train(client, learner_id)

    # No diagnostic file for the chapter: nothing to take, the seed is used.
    state.diagnostics = {}
    assert client.get(f"/api/diagnostic/{learner_id}").json()["required"] is False
    assert client.post(f"/api/chat/{learner_id}", json={"message": "Hi"}).status_code != 409

    # A file exists but the learner has not taken it: instruction is blocked.
    state.diagnostics = {"1": diagnostic}
    try:
        assert client.post(f"/api/lesson/{learner_id}").status_code == 409
        assert client.post(f"/api/chat/{learner_id}", json={"message": "Hi"}).status_code == 409
        assert client.post(f"/api/chat/{learner_id}/compare", json={"message": "Hi"}).status_code in (403, 409)

        # Taken: the gate lifts (anything but 409, e.g. 503 from the unconfigured LLM).
        r = client.post(f"/api/diagnostic/{learner_id}", json={"answers": RIGHT})
        assert r.status_code == 201
        assert client.post(f"/api/chat/{learner_id}", json={"message": "Hi"}).status_code != 409
    finally:
        state.diagnostics = {}


def test_gate_is_per_chapter(with_diagnostic: TestClient) -> None:
    learner_id = _onboard(with_diagnostic)
    _train(with_diagnostic, learner_id, chapter="2")  # no diagnostic for chapter 2
    assert with_diagnostic.post(f"/api/chat/{learner_id}", json={"message": "Hi"}).status_code != 409


def test_submit_stores_chapter_level_and_leaves_the_seed_alone(
    with_diagnostic: TestClient,
) -> None:
    c = with_diagnostic
    learner_id = _onboard(c, seed="none")
    _train(c, learner_id)
    body = c.post(f"/api/diagnostic/{learner_id}", json={"answers": RIGHT}).json()
    assert (body["experience_seed"], body["correct_count"], body["prior_knowledge"]) == (
        "none", 4, "moderate",
    )
    config = c.get(f"/api/config/{learner_id}").json()
    assert config["profile"]["prior_knowledge_seed"] == "none"  # not stored on the profile
    assert config["chapter_diagnostic"]["prior_knowledge"] == "moderate"
    assert c.post(f"/api/diagnostic/{learner_id}", json={"answers": [0] * 4}).status_code == 409


def test_other_chapter_still_uses_the_seed(with_diagnostic: TestClient) -> None:
    c = with_diagnostic
    learner_id = _onboard(c, seed="none")
    _train(c, learner_id)
    c.post(f"/api/diagnostic/{learner_id}", json={"answers": RIGHT})
    _train(c, learner_id, chapter="2")
    config = c.get(f"/api/config/{learner_id}").json()
    assert config["chapter_diagnostic"] is None
    assert config["attribution"]["explanation_depth"] == "pk_low"  # seed "none"


def test_summary_override_is_per_chapter_and_revertible(with_diagnostic: TestClient) -> None:
    c = with_diagnostic
    learner_id = _onboard(c)
    _train(c, learner_id)
    c.post(f"/api/diagnostic/{learner_id}", json={"answers": [3] * 4})  # all "don't know"
    derived = c.get(f"/api/diagnostic/{learner_id}").json()["result"]["derived"]

    r = c.put(f"/api/diagnostic/{learner_id}/override", json={"concreteness": 2})
    assert r.json()["effective"]["concreteness"] == 2
    assert r.json()["derived"] == derived  # the derived vector is never mutated
    _train(c, learner_id, chapter="2")
    assert c.get(f"/api/config/{learner_id}").json()["effective"]["concreteness"] == 5
    _train(c, learner_id)
    r = c.delete(f"/api/diagnostic/{learner_id}/override/concreteness")
    assert r.json()["effective"] == r.json()["derived"]


def test_invalid_answers_are_rejected(with_diagnostic: TestClient) -> None:
    c = with_diagnostic
    learner_id = _onboard(c)
    _train(c, learner_id)
    assert c.post(f"/api/diagnostic/{learner_id}", json={"answers": [0]}).status_code == 422
    assert c.post(f"/api/diagnostic/{learner_id}", json={"answers": [99] * 4}).status_code == 422


def test_instruction_routes_never_write_the_profile_or_diagnostics() -> None:
    """DR1, structurally: the routes that run instruction have no code path into
    the profile or diagnostic stores' write methods."""
    app_dir = Path(__file__).resolve().parents[1] / "app" / "api"
    for name in ("chat.py", "lesson.py", "conversations.py"):
        source = (app_dir / name).read_text()
        for write in ("chapter_diagnostics.create", "chapter_diagnostics.set_override", "profiles.create"):
            assert write not in source, f"{name} calls {write}"


# --- startup + staleness endpoint --------------------------------------------------


def test_startup_refuses_to_boot_on_an_invalid_diagnostic_yaml(
    postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main

    (tmp_path / "scoring_table.yaml").write_text(SCORING_PATH.read_text())
    course = tmp_path / "informationsmanagement"
    course.mkdir()
    bad = valid_raw()
    bad["items"].pop()
    (course / "1.yaml").write_text(yaml.safe_dump(bad))
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", tmp_path)

    with pytest.raises(DiagnosticFileError) as exc, TestClient(main.app):
        pass
    assert str(course / "1.yaml") in str(exc.value)


def test_startup_refuses_to_boot_on_an_invalid_scoring_table(
    postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main

    (tmp_path / "scoring_table.yaml").write_text("table: []\n")
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", tmp_path)
    with pytest.raises(DiagnosticFileError, match="scoring_table.yaml"), TestClient(main.app):
        pass


def test_stale_endpoint_lists_drifted_chapters_but_still_serves_them(
    db_conn, raw_client: TestClient  # type: ignore[no-untyped-def]
) -> None:
    from app.rag.chapter_text import chapter_text, source_hash
    from app.store.book_chunks import BookChunkRepository

    state = raw_client.app.state.itm  # type: ignore[attr-defined]
    chapter = next(c for c in state.curriculum if c.number == "1")
    BookChunkRepository(db_conn).replace_all(
        [(f"b-p{chapter.page_start}-0", "Aktueller Text", chapter.page_start, [0.0] * 1536)]
    )
    fresh = parse_diagnostic(valid_raw(source_hash=source_hash(chapter_text(db_conn, chapter))))
    stale = parse_diagnostic(valid_raw(source_hash="alt"))
    headers = {"Authorization": f"Bearer {login(raw_client, **SUPERUSER)}"}

    state.diagnostics = {"1": fresh}
    assert raw_client.get("/api/admin/diagnostics-stale", headers=headers).json() == {"stale": []}

    state.diagnostics = {"1": stale}
    try:
        body = raw_client.get("/api/admin/diagnostics-stale", headers=headers).json()
        assert [s["chapter_id"] for s in body["stale"]] == ["1"]
        assert body["stale"][0]["source_hash"] == "alt"
    finally:
        state.diagnostics = {}


def test_stale_endpoint_is_admin_only(client: TestClient) -> None:
    assert client.get("/api/admin/diagnostics-stale").status_code == 403
