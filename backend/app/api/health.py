from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.store.db import connection, ensure_schema

router = APIRouter(prefix="/api/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    database: str  # "ok" | "error: <reason>"


@router.get("", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    """Liveness + database reachability.

    Always returns a body; the status code is 503 when the database can't be
    reached, so an uptime monitor catches a sleeping/misconfigured Neon while a
    human still gets the reason. Also nudges the schema init that a DB-down
    cold start skipped.
    """
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        ensure_schema()
        return HealthResponse(status="ok", database="ok")
    except Exception as exc:  # noqa: BLE001 -- report any failure, don't crash
        response.status_code = 503
        return HealthResponse(status="degraded", database=f"error: {exc}")
