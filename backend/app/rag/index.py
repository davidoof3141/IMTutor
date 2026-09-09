"""Persistent local vector index over the course textbook.

Built offline by scripts/build_book_index.py, opened read-only by
app.rag.retriever at chat time. Not imported from core/ -- same layering
boundary as app/llm, since retrieval only participates in the chat turn, not
the deterministic control layer.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "book"
DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[2] / "data" / "chroma"


@lru_cache(maxsize=1)
def get_collection(index_dir: Path = DEFAULT_INDEX_DIR) -> Any:
    """Opens (or creates) the book collection, caching the client and embedding
    model for the life of the process -- loading the model is the expensive part.
    """
    client = chromadb.PersistentClient(path=str(index_dir))
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,  # type: ignore[arg-type]
    )


def warm(index_dir: Path = DEFAULT_INDEX_DIR) -> None:
    """Load the embedding model up front so the first chat turn isn't slow.

    No-op when no index has been built (retrieve() returns [] in that case, so
    there is nothing to warm). Safe to call from a background thread.
    """
    if not index_dir.exists():
        return
    get_collection(index_dir)
