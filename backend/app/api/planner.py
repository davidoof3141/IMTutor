from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import AppState, get_state
from app.core.constants import CURRENT_PLANNER_VERSION
from app.core.planner import PlannerTable
from app.core.step_templates import StepTemplates

router = APIRouter(prefix="/api/planner", tags=["planner"])


class PlannerResponse(BaseModel):
    planner_table: PlannerTable
    step_templates: StepTemplates


@router.get("", response_model=PlannerResponse)
def get_planner(
    version: str = CURRENT_PLANNER_VERSION, state: AppState = Depends(get_state)
) -> PlannerResponse:
    """Publishes the planner table and step templates a lesson plan is built
    from -- same reasoning as GET /api/rules: a third party must be able to
    reproduce a lesson plan without running the system."""
    if version not in state.planner_tables:
        raise HTTPException(status_code=404, detail=f"unknown planner version: {version}")
    return PlannerResponse(
        planner_table=state.planner_tables[version],
        step_templates=state.step_templates[version],
    )
