from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import Repos, get_repos, require_admin
from app.store.comparisons import VariantKind
from app.store.users import User

router = APIRouter(prefix="/api/admin/stats", tags=["admin"])


class KindPreferenceCount(BaseModel):
    kind: VariantKind
    count: int


class ReasonCount(BaseModel):
    reason: str
    count: int


class OverrideFieldCount(BaseModel):
    field: str
    count: int


class AdminStatsResponse(BaseModel):
    comparisons_decided: int
    comparisons_pending: int
    preference_by_kind: list[KindPreferenceCount]
    reason_counts: list[ReasonCount]
    override_changes_total: int
    override_changes_by_field: list[OverrideFieldCount]


@router.get("", response_model=AdminStatsResponse)
def get_admin_stats(
    _: User = Depends(require_admin),
    repos: Repos = Depends(get_repos),
) -> AdminStatsResponse:
    """Aggregate numbers for the admin dashboard: how often the personalized
    vs. generic answer was preferred in the A/B comparison, which reasons
    learners gave, and which scrutability-interface parameters get edited
    most."""
    decided, pending = repos.comparisons.decided_and_pending_counts()
    return AdminStatsResponse(
        comparisons_decided=decided,
        comparisons_pending=pending,
        preference_by_kind=[
            KindPreferenceCount(**row) for row in repos.comparisons.kind_preference_counts()
        ],
        reason_counts=[ReasonCount(**row) for row in repos.comparisons.reason_counts()],
        override_changes_total=repos.override_changes.total(),
        override_changes_by_field=[
            OverrideFieldCount(**row) for row in repos.override_changes.field_counts()
        ],
    )
