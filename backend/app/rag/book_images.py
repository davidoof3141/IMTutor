"""Runtime lookup over the manifest scripts/extract_book_images.py builds.

Opened read-only by app.api.book_images (serving bytes) and app.api.chat
(picking images for the pages retrieval already surfaced). Not imported from
core/ -- same layering boundary as app.rag.retriever.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.rag.images import DEFAULT_IMAGES_DIR

DEFAULT_MAX_IMAGES = 4


class BookImageMeta(BaseModel):
    id: str
    page: int
    content_type: str
    width: int
    height: int
    filename: str


@lru_cache(maxsize=1)
def load_manifest(images_dir: Path = DEFAULT_IMAGES_DIR) -> list[BookImageMeta]:
    """[] if no extraction has been run yet -- images are best-effort, same
    spirit as an unbuilt RAG index."""
    manifest_path = images_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    entries = json.loads(manifest_path.read_text())
    return [BookImageMeta(**entry) for entry in entries]


def images_for_pages(
    pages: list[int],
    *,
    limit: int = DEFAULT_MAX_IMAGES,
    images_dir: Path = DEFAULT_IMAGES_DIR,
) -> list[BookImageMeta]:
    """Images on `pages`, most-relevant page first (callers pass pages in
    retrieval order), deduplicated and capped to `limit`."""
    by_page: dict[int, list[BookImageMeta]] = {}
    for meta in load_manifest(images_dir):
        by_page.setdefault(meta.page, []).append(meta)

    result: list[BookImageMeta] = []
    seen_pages: set[int] = set()
    for page in pages:
        if page in seen_pages or page not in by_page:
            continue
        seen_pages.add(page)
        result.extend(by_page[page])
        if len(result) >= limit:
            break
    return result[:limit]


def find_image(image_id: str, *, images_dir: Path = DEFAULT_IMAGES_DIR) -> BookImageMeta | None:
    return next((m for m in load_manifest(images_dir) if m.id == image_id), None)
