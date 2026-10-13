"""Maintenance view: which chapters' diagnostics no longer match the book index.

Regeneration is an offline maintenance action (scripts/generate_diagnostics.py);
a stale diagnostic keeps being served, this only lists it.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import AppState, get_state, require_admin
from app.core.diagnostic import stale_chapters
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
