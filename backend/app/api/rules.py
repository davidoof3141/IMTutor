from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import AppState, get_state
from app.core.clauses import ClauseCatalogue
from app.core.constants import CURRENT_RULESET_VERSION
from app.core.rules import RuleSet

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RulesResponse(BaseModel):
    ruleset: RuleSet
    catalogue: ClauseCatalogue


@router.get("", response_model=RulesResponse)
def get_rules(
    version: str = CURRENT_RULESET_VERSION, state: AppState = Depends(get_state)
) -> RulesResponse:
    if version not in state.rulesets:
        raise HTTPException(status_code=404, detail=f"unknown ruleset version: {version}")
    return RulesResponse(ruleset=state.rulesets[version], catalogue=state.catalogues[version])
