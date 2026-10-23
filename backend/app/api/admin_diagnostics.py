"""Maintenance view: which chapters' diagnostics no longer match the book index.

Regeneration is an offline maintenance action (scripts/generate_diagnostics.py);
a stale diagnostic keeps being served, this only lists it.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import AppState, Repos, get_repos, get_state, require_admin
from app.core.diagnostic import stale_chapters
from app.core.profile import PriorKnowledge
from app.rag.chapter_text import current_hashes
from app.store.db import connection
from app.store.users import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


class StaleDiagnostic(BaseModel):
    chapter_id: str
    title: str
    source_hash: str
    current_hash: str


class StaleDiagnosticsResponse(BaseModel):
    stale: list[StaleDiagnostic]


@router.get("/diagnostics-stale", response_model=StaleDiagnosticsResponse)
def diagnostics_stale(
    state: AppState = Depends(get_state), _: User = Depends(require_admin)
) -> StaleDiagnosticsResponse:
    with connection() as conn:
        hashes = current_hashes(conn, state.curriculum)
    titles = {c.number: c.title for c in state.curriculum}
    return StaleDiagnosticsResponse(
        stale=[
            StaleDiagnostic(
                chapter_id=chapter_id,
                title=titles.get(chapter_id, ""),
                source_hash=state.diagnostics[chapter_id].source_hash,
                current_hash=hashes[chapter_id],
            )
            for chapter_id in stale_chapters(state.diagnostics, hashes)
        ]
    )


class DiagnosticResultRow(BaseModel):
    username: str
    chapter_id: str
    chapter_title: str
    correct_count: int
    item_count: int | None  # None when the chapter's diagnostic is no longer loaded
    self_estimate: PriorKnowledge  # onboarding seed, as it was when the quiz was taken
    quiz_level: PriorKnowledge
    taken_at: str


class DiagnosticResultsResponse(BaseModel):
    results: list[DiagnosticResultRow]


@router.get("/diagnostic-results", response_model=DiagnosticResultsResponse)
def diagnostic_results(
    state: AppState = Depends(get_state),
    repos: Repos = Depends(get_repos),
    _: User = Depends(require_admin),
) -> DiagnosticResultsResponse:
    """Self-estimate (onboarding) vs. quiz result, one row per learner and chapter."""
    titles = {c.number: c.title for c in state.curriculum}
    rows = []
    for row in repos.chapter_diagnostics.list_with_usernames():
        key = row["diagnostic_key"]
        diagnostic = state.diagnostics.get(key)
        rows.append(
            DiagnosticResultRow(
                username=row["username"],
                chapter_id=key,
                chapter_title=titles.get(key, ""),
                correct_count=row["correct_count"],
                item_count=len(diagnostic.items) if diagnostic else None,
                self_estimate=row["experience_seed"],
                quiz_level=row["prior_knowledge"],
                taken_at=row["created_at"].isoformat(),
            )
        )
    return DiagnosticResultsResponse(results=rows)
