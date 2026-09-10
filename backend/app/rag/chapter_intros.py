"""Runtime lookup over the manifest scripts/generate_chapter_intros.py builds.

Pre-generated, chapter/section-keyed welcome messages plus a few starter
questions -- one fixed set per selection, not personalized per learner (a
deliberate trade-off: instant, free, and reproducible to serve, at the cost
of not following the learner's configured style for this one message).
Opened read-only by app.api.chapter_intro; the actual, LLM-touching
generation lives in the script, not here -- same split as app.rag.book_images
vs. images.py.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DEFAULT_CHAPTER_INTROS_PATH = Path(__file__).resolve().parents[2] / "data" / "chapter_intros.json"


class ChapterIntro(BaseModel):
    """One selection's welcome message and its starter questions."""

    model_config = ConfigDict(frozen=True)

    text: str
    # Fixed suggestions shown as chips before the learner has said anything --
    # tailored to this chapter/section, unlike the generic fallback in the UI.
    starters: tuple[str, ...] = ()


def intro_key(chapter_number: str, section_number: str | None) -> str:
    return chapter_number if section_number is None else f"{chapter_number}:{section_number}"


@lru_cache(maxsize=1)
def load_chapter_intros(path: Path = DEFAULT_CHAPTER_INTROS_PATH) -> dict[str, ChapterIntro]:
    """{} if the generation script hasn't been run yet -- best-effort, same
    spirit as an unbuilt RAG index.

    A bare string value is the pre-starters manifest format; it still loads,
    just with no starter questions (the UI falls back to its generic set).
    """
    if not path.exists():
        return {}
    raw: dict[str, object] = json.loads(path.read_text())
    intros: dict[str, ChapterIntro] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            intros[key] = ChapterIntro(text=value)
        else:
            intros[key] = ChapterIntro.model_validate(value)
    return intros
