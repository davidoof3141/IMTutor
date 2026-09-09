from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.rag.chunking import BOOK_PATH
from app.store.users import User

router = APIRouter(prefix="/api/book", tags=["book"])


@router.get("/pdf")
def get_book_pdf(user: User = Depends(get_current_user)) -> FileResponse:
    """Serves the course textbook PDF so a reference link can open it at a
    specific page (`<url>#page=N`). Shared course material, not learner data --
    any authenticated user may fetch it, no ownership check."""
    return FileResponse(BOOK_PATH, media_type="application/pdf")
