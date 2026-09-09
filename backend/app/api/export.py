from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import Repos, authorize_learner, get_current_user, get_repos
from app.store.users import User

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{learner_id}")
def export_log(
    learner_id: str,
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    authorize_learner(learner_id, user, repos)
    return repos.turn_logs.read_all(learner_id)
