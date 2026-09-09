"""Splits the course textbook into overlapping, page-tagged chunks for retrieval.

Pure text processing -- no embedding, no I/O beyond reading the PDF. Kept
separate from index.py so chunking logic is testable without loading a model.
"""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

BOOK_PATH = Path(__file__).resolve().parents[2] / "Krcmar2015_Informationsmanagement.pdf"

CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 200


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    page: int  # 1-indexed


def extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Returns (1-indexed page number, whitespace-collapsed text) for non-empty pages."""
    reader = PdfReader(str(pdf_path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = " ".join((page.extract_text() or "").split())
        if text:
            pages.append((page_number, text))
    return pages


def chunk_text(text: str, *, page: int, source: str) -> list[Chunk]:
    """Splits one page's text into overlapping fixed-size chunks."""
    if not text:
        return []
    chunks = []
    start = 0
    index = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE_CHARS, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(chunk_id=f"{source}-p{page}-{index}", text=piece, page=page))
            index += 1
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP_CHARS
    return chunks


def chunk_book(pdf_path: Path) -> list[Chunk]:
    source = pdf_path.stem
    chunks: list[Chunk] = []
    for page, text in extract_pages(pdf_path):
        chunks.extend(chunk_text(text, page=page, source=source))
    return chunks
