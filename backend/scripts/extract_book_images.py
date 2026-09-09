"""Extracts the figures/diagrams embedded in the course textbook PDF so the
frontend can display them alongside retrieved passages.

Run after the book PDF changes, or once before the first chat request:

    uv run python scripts/extract_book_images.py
"""

import json
import shutil

from app.rag.chunking import BOOK_PATH
from app.rag.images import (
    CONTENT_TYPE_EXTENSION,
    DEFAULT_IMAGES_DIR,
    extract_images,
    extract_vector_figures,
)


def main() -> None:
    if DEFAULT_IMAGES_DIR.exists():
        shutil.rmtree(DEFAULT_IMAGES_DIR)
    DEFAULT_IMAGES_DIR.mkdir(parents=True)

    raster_images = extract_images(BOOK_PATH)
    vector_images = extract_vector_figures(
        BOOK_PATH, skip_pages={image.page for image in raster_images}
    )
    images = raster_images + vector_images

    manifest = []
    for image in images:
        extension = CONTENT_TYPE_EXTENSION[image.content_type]
        filename = f"{image.image_id}.{extension}"
        (DEFAULT_IMAGES_DIR / filename).write_bytes(image.data)
        manifest.append(
            {
                "id": image.image_id,
                "page": image.page,
                "content_type": image.content_type,
                "width": image.width,
                "height": image.height,
                "filename": filename,
            }
        )
    (DEFAULT_IMAGES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    pages = len({entry["page"] for entry in manifest})
    print(f"Extracted {len(manifest)} images from {pages} pages into {DEFAULT_IMAGES_DIR}")


if __name__ == "__main__":
    main()
