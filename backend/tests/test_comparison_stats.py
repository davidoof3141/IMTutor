from app.store.comparisons import ComparisonRepository
from app.store.db import Conn


def _decide(repo: ComparisonRepository, conn: Conn, learner: str, picked_kind: str) -> None:
    conn.execute(
        "INSERT INTO conversations (id, learner_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (f"c-{learner}", learner),
    )
    conn.commit()
    other = "generic" if picked_kind == "personalized" else "personalized"
    cid = repo.create_pending(
        conversation_id=f"c-{learner}",
        learner_id=learner,
        learner_message="q",
        ruleset_version="v",
        personalized_vector={},
        baseline_vector={},
        variant_a_kind=picked_kind,  # type: ignore[arg-type]
        variant_b_kind=other,  # type: ignore[arg-type]
        book_context="",
        book_image_refs=[],
        page_refs=[],
        attachment_ids=[],
        lesson_id=None,
        study_mode=None,
    )
    repo.finalize(cid, chosen_variant="a", reasons=[], other_reason=None)


def test_learner_preference_counts(db_conn: Conn) -> None:
    repo = ComparisonRepository(db_conn)
    for kind in ("personalized", "personalized", "generic"):  # l1: personalized more
        _decide(repo, db_conn, "l1", kind)
    for kind in ("generic", "generic", "personalized"):  # l2: generic more
        _decide(repo, db_conn, "l2", kind)
    for kind in ("personalized", "generic"):  # l3: tie
        _decide(repo, db_conn, "l3", kind)

    assert repo.learner_preference_counts() == {
        "learners": 3,
        "personalized_more": 1,
        "generic_more": 1,
        "tied": 1,
    }
