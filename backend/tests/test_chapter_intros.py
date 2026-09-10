import json
from pathlib import Path

from app.rag.chapter_intros import intro_key, load_chapter_intros


def test_intro_key_whole_chapter_vs_section() -> None:
    assert intro_key("3", None) == "3"
    assert intro_key("3", "3.2") == "3:3.2"


def test_missing_manifest_loads_as_empty(tmp_path: Path) -> None:
    assert load_chapter_intros(tmp_path / "nope.json") == {}


def test_loads_new_format_with_starters(tmp_path: Path) -> None:
    path = tmp_path / "intros.json"
    path.write_text(
        json.dumps({"1": {"text": "Hallo", "starters": ["Frage eins?", "Frage zwei?"]}})
    )
    intros = load_chapter_intros(path)
    assert intros["1"].text == "Hallo"
    assert intros["1"].starters == ("Frage eins?", "Frage zwei?")


def test_loads_legacy_bare_string_format_with_no_starters(tmp_path: Path) -> None:
    path = tmp_path / "intros.json"
    path.write_text(json.dumps({"1": "Nur der Text, keine Fragen."}))
    intros = load_chapter_intros(path)
    assert intros["1"].text == "Nur der Text, keine Fragen."
    assert intros["1"].starters == ()
