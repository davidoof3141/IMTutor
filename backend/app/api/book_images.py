from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.rag.book_images import find_image
from app.rag.images import DEFAULT_IMAGES_DIR
from app.store.users import User

router = APIRouter(prefix="/api/book-images", tags=["book-images"])


@router.get("/{image_id}")
def get_book_image(image_id: str, user: User = Depends(get_current_user)) -> FileResponse:
    """Serves one extracted figure. Shared course material, not learner data --
    any authenticated user may fetch any image, no ownership check."""
    meta = find_image(image_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(DEFAULT_IMAGES_DIR / meta.filename, media_type=meta.content_type)
