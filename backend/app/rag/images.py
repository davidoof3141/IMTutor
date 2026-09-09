"""Extracts the figures/diagrams embedded in the course textbook PDF.

Offline, script-driven extraction -- no DB, no caching. Kept separate from
book_images.py, which loads the resulting manifest at chat time, the same
split as chunking.py (pure PDF extraction) vs index.py (runtime index).
"""

import io
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image
from pypdf import PdfReader

DEFAULT_IMAGES_DIR = Path(__file__).resolve().parents[2] / "data" / "book_images"

# Below this in either dimension, an embedded image is almost always a
# decorative rule, bullet, or scan artifact rather than a real figure.
MIN_DIMENSION = 100

CONTENT_TYPE_EXTENSION = {"image/jpeg": "jpg", "image/png": "png"}

# --- Vector-drawn figures -------------------------------------------------
#
# Most of this book's diagrams (flowcharts, process models, ...) are drawn as
# PDF vector paths, not embedded raster images, so extract_images() above
# can't see them. extract_vector_figures() finds them instead by clustering
# each page's drawing operators -- a diagram's boxes/arrows/sub-panels sit
# close together and touch or nearly touch, while unrelated page content
# (running text draws no paths at all) does not -- then rasterizes each
# cluster's bounding box. This is a geometric heuristic, not true figure
# detection: it can occasionally crop a table's grid lines, or merge two
# figures that happen to sit close together on the same page.

# Bridges the gaps between a diagram's boxes, arrows, and connector lines
# (tuned empirically -- large enough to unify a flowchart's separate shapes
# and a multi-panel figure's sub-panels, small enough to leave unrelated
# content elsewhere on the page in its own cluster).
VECTOR_CLUSTER_MARGIN = 35.0

# A thin rect spanning most of the page is a header/footer/table rule, not
# part of a diagram.
RULE_LINE_FRACTION = 0.6
RULE_LINE_MAX_DIM = 3.0

# Clusters smaller than this are almost always stray marks, not a figure.
MIN_CLUSTER_PATHS = 5
MIN_CLUSTER_WIDTH = 60.0
MIN_CLUSTER_HEIGHT = 40.0

CROP_PADDING = 10.0
RENDER_ZOOM = 2.0
MAX_VECTOR_FIGURES_PER_PAGE = 3


@dataclass(frozen=True)
class BookImage:
    image_id: str
    page: int  # 1-indexed
    content_type: str
    data: bytes
    width: int
    height: int


def extract_images(pdf_path: Path) -> list[BookImage]:
    """Returns every large-enough embedded image, page order, re-encoded to a
    browser-displayable format."""
    reader = PdfReader(str(pdf_path))
    source = pdf_path.stem
    images: list[BookImage] = []
    for page_number, page in enumerate(reader.pages, start=1):
        for index, xobject_image in enumerate(page.images):
            pil_image = xobject_image.image
            if pil_image is None:
                continue
            width, height = pil_image.size
            if width < MIN_DIMENSION or height < MIN_DIMENSION:
                continue
            content_type, data = _encode(pil_image)
            images.append(
                BookImage(
                    image_id=f"{source}-p{page_number}-{index}",
                    page=page_number,
                    content_type=content_type,
                    data=data,
                    width=width,
                    height=height,
                )
            )
    return images


def _is_rule_line(rect: "pymupdf.Rect", page_width: float, page_height: float) -> bool:
    horizontal = rect.width > RULE_LINE_FRACTION * page_width and rect.height < RULE_LINE_MAX_DIM
    vertical = rect.height > RULE_LINE_FRACTION * page_height and rect.width < RULE_LINE_MAX_DIM
    return bool(horizontal or vertical)


def _cluster_drawing_rects(rects: list["pymupdf.Rect"]) -> list["pymupdf.Rect"]:
    """Unions rects within VECTOR_CLUSTER_MARGIN of each other, then drops
    clusters too small to plausibly be a figure. Largest first, capped to
    MAX_VECTOR_FIGURES_PER_PAGE."""
    n = len(rects)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    margin = VECTOR_CLUSTER_MARGIN
    expanded = [
        pymupdf.Rect(r.x0 - margin, r.y0 - margin, r.x1 + margin, r.y1 + margin) for r in rects
    ]
    for i in range(n):
        for j in range(i + 1, n):
            if expanded[i].intersects(expanded[j]):
                union(i, j)

    groups: dict[int, list[pymupdf.Rect]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(rects[i])

    clusters = []
    for members in groups.values():
        if len(members) < MIN_CLUSTER_PATHS:
            continue
        x0 = min(r.x0 for r in members)
        y0 = min(r.y0 for r in members)
        x1 = max(r.x1 for r in members)
        y1 = max(r.y1 for r in members)
        if (x1 - x0) < MIN_CLUSTER_WIDTH or (y1 - y0) < MIN_CLUSTER_HEIGHT:
            continue
        clusters.append(pymupdf.Rect(x0, y0, x1, y1))

    clusters.sort(key=lambda r: r.width * r.height, reverse=True)
    return clusters[:MAX_VECTOR_FIGURES_PER_PAGE]


def extract_vector_figures(
    pdf_path: Path, *, skip_pages: Collection[int] = frozenset()
) -> list[BookImage]:
    """Finds diagrams drawn as PDF vector paths rather than embedded raster
    images (see module docstring above) and rasterizes each one. `skip_pages`
    lets the caller skip pages extract_images() already found a raster figure
    on."""
    doc = pymupdf.open(str(pdf_path))
    source = pdf_path.stem
    images: list[BookImage] = []
    try:
        for page_number in range(1, doc.page_count + 1):
            if page_number in skip_pages:
                continue
            page = doc[page_number - 1]
            page_w, page_h = page.rect.width, page.rect.height
            rects = [
                d["rect"]
                for d in page.get_drawings()
                if d["rect"].width > 0
                and d["rect"].height > 0
                and not _is_rule_line(d["rect"], page_w, page_h)
            ]
            for index, rect in enumerate(_cluster_drawing_rects(rects)):
                padded = pymupdf.Rect(
                    max(rect.x0 - CROP_PADDING, 0),
                    max(rect.y0 - CROP_PADDING, 0),
                    min(rect.x1 + CROP_PADDING, page_w),
                    min(rect.y1 + CROP_PADDING, page_h),
                )
                pixmap = page.get_pixmap(
                    clip=padded, matrix=pymupdf.Matrix(RENDER_ZOOM, RENDER_ZOOM)
                )
                images.append(
                    BookImage(
                        image_id=f"{source}-p{page_number}-v{index}",
                        page=page_number,
                        content_type="image/png",
                        data=pixmap.tobytes("png"),
                        width=pixmap.width,
                        height=pixmap.height,
                    )
                )
    finally:
        doc.close()
    return images


def _encode(image: Image.Image) -> tuple[str, bytes]:
    """JPEGs stay JPEG; everything else (PNG, TIFF, bilevel scans, ...)
    becomes PNG, since browsers can't render most other PDF image formats."""
    buffer = io.BytesIO()
    if image.format == "JPEG" and image.mode in ("RGB", "L"):
        image.save(buffer, format="JPEG", quality=90)
        return "image/jpeg", buffer.getvalue()
    if image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGB")
    image.save(buffer, format="PNG")
    return "image/png", buffer.getvalue()
