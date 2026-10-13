"""Onboarding yields a complete profile; preferences stay out of the mapping."""

import pytest
from fastapi.testclient import TestClient

from app.core.assembler import assemble
from app.core.clauses import ClauseCatalogue
from app.core.mapping import derive
from app.core.profile import MAPPING_INPUTS
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
    assert profile["learner_type"] == "none"
    for removed in ("role", "address_form", "prior_experience", "goal"):
        assert removed not in profile


def test_onboarding_stores_all_four_inputs_and_both_preferences(client: TestClient) -> None:
    sent = {
        "prior_knowledge_seed": "high",
        "learning_goal": "orientation",
        "retention_horizon": "long_term",
        "industry": "energy",
        "simplified_language": True,
        "presentation_style": "verbose",
        "learner_type": "auditiv",
    }
    learner_id = client.post("/api/onboarding", json=sent).json()["profile"]["learner_id"]
    stored = client.get(f"/api/config/{learner_id}").json()["profile"]
    for key, value in sent.items():
        assert stored[key] == value


def test_exam_date_is_not_accepted(client: TestClient) -> None:
    r = client.post("/api/onboarding", json={"exam_date": "2099-01-01"})
    assert r.status_code == 200
    assert "exam_date" not in r.json()["profile"]
    assert r.json()["profile"]["retention_horizon"] == "1_to_3_months"  # ignored: default


def test_identical_profile_gives_byte_equal_vector(ruleset: RuleSet) -> None:
    a = derive(make_profile(industry="finance", learning_goal="applied"), ruleset)
    b = derive(make_profile(industry="finance", learning_goal="applied"), ruleset)
    assert a[0].model_dump_json().encode() == b[0].model_dump_json().encode()
    assert repr(a[1]).encode() == repr(b[1]).encode()


def test_preferences_never_reach_the_mapping(ruleset: RuleSet) -> None:
    base = derive(make_profile(), ruleset)
    for style in ("concise", "balanced", "verbose"):
        for simple in (True, False):
            for learner_type in ("none", "visuell", "auditiv", "kommunikativ", "motorisch"):
                other = derive(
                    make_profile(
                        simplified_language=simple,
                        presentation_style=style,  # type: ignore[arg-type]
                        learner_type=learner_type,  # type: ignore[arg-type]
                    ),
                    ruleset,
                )
                assert other == base
    for rule in ruleset.rules:
        assert set(rule.when) <= set(MAPPING_INPUTS)


def test_preferences_only_add_fixed_clauses_in_assembly(
    ruleset: RuleSet, catalogue: ClauseCatalogue
) -> None:
    profile = make_profile(
        simplified_language=True, presentation_style="concise", learner_type="visuell"
    )
    vector, _ = derive(profile, ruleset)
    plain = assemble(vector, catalogue)
    with_prefs = assemble(vector, catalogue, profile.preferences)
    assert with_prefs.startswith(plain)
    extra = with_prefs[len(plain) :].strip().split("\n")
    assert extra == [
        catalogue.preferences["simplified_language"][True],
        catalogue.preferences["presentation_style"]["concise"],
        catalogue.preferences["learner_type"]["visuell"],
    ]


def test_mapping_inputs_cover_the_profile_fields_that_feed_rules() -> None:
    assert len(MAPPING_FIELDS) == len(MAPPING_INPUTS) == 4


# --- the retention / goal / prior-knowledge rules ---------------------------


@pytest.mark.parametrize(
    "horizon, gap_days",
    [("within_2_weeks", 2), ("1_to_3_months", 7), ("long_term", 14)],
)
def test_retention_horizon_sets_review_schedule_gap_days(
    ruleset: RuleSet, horizon: str, gap_days: int
) -> None:
    vector, attribution = derive(make_profile(retention_horizon=horizon), ruleset)  # type: ignore[arg-type]
    assert vector.review_schedule == gap_days
    assert attribution["review_schedule"] == f"retention_{horizon}"


@pytest.mark.parametrize(
    "goal, frequency",
    [
        ("certification", "every_topic"),
        ("applied", "every_second_topic"),
        ("orientation", "on_request"),
    ],
)
def test_assessment_frequency_depends_on_goal_only(
    ruleset: RuleSet, goal: str, frequency: str
) -> None:
    for horizon in ("within_2_weeks", "1_to_3_months", "long_term"):
        vector, attribution = derive(
            make_profile(learning_goal=goal, retention_horizon=horizon),  # type: ignore[arg-type]
            ruleset,
        )
        assert vector.assessment_frequency == frequency
        assert attribution["assessment_frequency"] == f"goal_{goal}"


def test_no_rule_lets_retention_touch_assessment_or_goal_touch_review(ruleset: RuleSet) -> None:
    for rule in ruleset.rules:
        if "retention_horizon" in rule.when:
            assert set(rule.set) == {"review_schedule"}
        if "learning_goal" in rule.when:
            assert set(rule.set) == {"assessment_frequency"}


@pytest.mark.parametrize(
    "level, concreteness",
    [("none", 5), ("low", 5), ("moderate", 3), ("high", 1)],
)
def test_prior_knowledge_sets_concreteness(
    ruleset: RuleSet, level: str, concreteness: int
) -> None:
    vector, attribution = derive(make_profile(prior_knowledge_seed=level), ruleset)  # type: ignore[arg-type]
    assert vector.concreteness == concreteness
    assert attribution["concreteness"].startswith("pk_")


@pytest.mark.parametrize(
    "level, register",
    [("none", "polite"), ("low", "polite"), ("moderate", "direct"), ("high", "direct")],
)
def test_prior_knowledge_sets_register(ruleset: RuleSet, level: str, register: str) -> None:
    vector, attribution = derive(make_profile(prior_knowledge_seed=level), ruleset)  # type: ignore[arg-type]
    assert vector.register == register
    assert attribution["register"].startswith("pk_")


def test_chapter_level_drives_concreteness_and_register_not_the_seed(ruleset: RuleSet) -> None:
    profile = make_profile(prior_knowledge_seed="none")
    vector, _ = derive(profile, ruleset, "high")
    assert (vector.concreteness, vector.register) == (1, "direct")


def test_review_schedule_has_a_fixed_prompt_clause(
    ruleset: RuleSet, catalogue: ClauseCatalogue
) -> None:
    vector, _ = derive(make_profile(retention_horizon="long_term"), ruleset)
    assert "14 Tagen" in assemble(vector, catalogue)
