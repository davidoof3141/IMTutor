"""Onboarding yields a complete profile; preferences stay out of the mapping."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.assembler import assemble
from app.core.clauses import ClauseCatalogue
from app.core.mapping import derive
from app.core.profile import MAPPING_INPUTS, band_from_exam_date
from app.core.rules import RuleSet
from tests.conftest import make_profile

MAPPING_FIELDS = ("prior_knowledge_seed", "learning_goal", "retention_horizon", "industry")


def test_onboarding_with_no_answers_yields_explicit_defaults(client: TestClient) -> None:
    profile = client.post("/api/onboarding", json={}).json()["profile"]
    assert profile["prior_knowledge_seed"] == "none"
    assert profile["learning_goal"] == "applied"
    assert profile["retention_horizon"] == "1_to_3_months"
    assert profile["industry"] == "neutral"
    assert profile["simplified_language"] is False
    assert profile["presentation_style"] == "balanced"
    for removed in ("role", "learner_type", "address_form", "prior_experience", "goal"):
        assert removed not in profile


def test_onboarding_stores_all_four_inputs_and_both_preferences(client: TestClient) -> None:
    sent = {
        "prior_knowledge_seed": "high",
        "learning_goal": "orientation",
        "retention_horizon": "long_term",
        "industry": "energy",
        "simplified_language": True,
        "presentation_style": "verbose",
    }
    learner_id = client.post("/api/onboarding", json=sent).json()["profile"]["learner_id"]
    stored = client.get(f"/api/config/{learner_id}").json()["profile"]
    for key, value in sent.items():
        assert stored[key] == value


def test_exam_date_is_converted_once_to_a_stored_band(client: TestClient) -> None:
    exam = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    profile = client.post("/api/onboarding", json={"exam_date": exam}).json()["profile"]
    assert profile["retention_horizon"] == "1_to_3_months"
    assert "exam_date" not in profile  # only the band is stored


def test_exam_date_and_band_together_are_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/onboarding",
        json={"exam_date": "2099-01-01", "retention_horizon": "long_term"},
    )
    assert r.status_code == 422


def test_past_exam_date_is_rejected(client: TestClient) -> None:
    exam = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    assert client.post("/api/onboarding", json={"exam_date": exam}).status_code == 422


@pytest.mark.parametrize(
    "days, band",
    [
        (0, "within_2_weeks"),
        (14, "within_2_weeks"),
        (15, "1_to_3_months"),
        (92, "1_to_3_months"),
        (93, "long_term"),
    ],
)
def test_band_from_exam_date_boundaries(days: int, band: str) -> None:
    today = date(2026, 1, 1)
    assert band_from_exam_date(today + timedelta(days=days), today) == band


def test_identical_profile_gives_byte_equal_vector(ruleset: RuleSet) -> None:
    a = derive(make_profile(industry="finance", learning_goal="applied"), ruleset)
    b = derive(make_profile(industry="finance", learning_goal="applied"), ruleset)
    assert a[0].model_dump_json().encode() == b[0].model_dump_json().encode()
    assert repr(a[1]).encode() == repr(b[1]).encode()


def test_preferences_never_reach_the_mapping(ruleset: RuleSet) -> None:
    base = derive(make_profile(), ruleset)
    for style in ("concise", "balanced", "verbose"):
        for simple in (True, False):
            other = derive(
                make_profile(simplified_language=simple, presentation_style=style), ruleset  # type: ignore[arg-type]
            )
            assert other == base
    for rule in ruleset.rules:
        assert set(rule.when) <= set(MAPPING_INPUTS)


def test_preferences_only_add_fixed_clauses_in_assembly(
    ruleset: RuleSet, catalogue: ClauseCatalogue
) -> None:
    profile = make_profile(simplified_language=True, presentation_style="concise")
    vector, _ = derive(profile, ruleset)
    plain = assemble(vector, catalogue)
    with_prefs = assemble(vector, catalogue, profile.preferences)
    assert with_prefs.startswith(plain)
    extra = with_prefs[len(plain) :].strip().split("\n")
    assert extra == [
        catalogue.preferences["simplified_language"][True],
        catalogue.preferences["presentation_style"]["concise"],
    ]


def test_mapping_inputs_cover_the_profile_fields_that_feed_rules() -> None:
    assert len(MAPPING_FIELDS) == len(MAPPING_INPUTS) == 4
