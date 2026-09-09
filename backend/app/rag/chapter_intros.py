"""Runtime lookup over the manifest scripts/generate_chapter_intros.py builds.

Pre-generated, chapter/section-keyed welcome messages -- one fixed text per
selection, not personalized per learner (a deliberate trade-off: instant,
free, and reproducible to serve, at the cost of not following the learner's
configured style for this one message). Opened read-only by
app.api.chapter_intro; the actual, LLM-touching generation lives in the
script, not here -- same split as app.rag.book_images vs. images.py.
"""

import json
from functools import lru_cache
from pathlib import Path

DEFAULT_CHAPTER_INTROS_PATH = Path(__file__).resolve().parents[2] / "data" / "chapter_intros.json"


def intro_key(chapter_number: str, section_number: str | None) -> str:
    return chapter_number if section_number is None else f"{chapter_number}:{section_number}"


@lru_cache(maxsize=1)
def load_chapter_intros(path: Path = DEFAULT_CHAPTER_INTROS_PATH) -> dict[str, str]:
    """{} if the generation script hasn't been run yet -- best-effort, same
    spirit as an unbuilt RAG index."""
    if not path.exists():
        return {}
    result: dict[str, str] = json.loads(path.read_text())
    return result
