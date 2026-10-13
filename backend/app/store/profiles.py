import psycopg

from app.core.profile import Profile
from app.store.db import Conn


class ProfileAlreadyExists(Exception):
    pass


class ProfileRepository:
    """Write-once storage for Profile records.

    No update method by design (invariant: Profile is write-once) -- a new
    onboarding submission must create a new learner_id, never mutate a
    stored profile.
    """

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def create(self, profile: Profile) -> None:
        try:
            self._conn.execute(
                """
                INSERT INTO profiles
                    (learner_id, user_id, prior_knowledge_seed, learning_goal,
                     retention_horizon, industry, simplified_language,
                     presentation_style, learner_type, ruleset_version, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    profile.learner_id,
                    profile.user_id,
                    profile.prior_knowledge_seed,
                    profile.learning_goal,
                    profile.retention_horizon,
                    profile.industry,
                    profile.simplified_language,
                    profile.presentation_style,
                    profile.learner_type,
                    profile.ruleset_version,
                    profile.created_at.isoformat(),
                ),
            )
            self._conn.commit()
        except psycopg.errors.UniqueViolation as exc:
            self._conn.rollback()
            raise ProfileAlreadyExists(profile.learner_id) from exc

    def get(self, learner_id: str) -> Profile | None:
        row = self._conn.execute(
            "SELECT * FROM profiles WHERE learner_id = %s", (learner_id,)
        ).fetchone()
        if row is None:
            return None
        return Profile(
            learner_id=row["learner_id"],
            user_id=row["user_id"],
            prior_knowledge_seed=row["prior_knowledge_seed"],
            learning_goal=row["learning_goal"],
            retention_horizon=row["retention_horizon"],
            industry=row["industry"],
            simplified_language=row["simplified_language"],
            presentation_style=row["presentation_style"],
            # NULL on legacy rows whose column predates this field
            learner_type=row["learner_type"] or "none",
            ruleset_version=row["ruleset_version"],
            created_at=row["created_at"],
        )

    def get_learner_id_for_user(self, user_id: str) -> str | None:
        """The most recent profile owned by a user, if any."""
        row = self._conn.execute(
            """
            SELECT learner_id FROM profiles
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return None if row is None else str(row["learner_id"])
