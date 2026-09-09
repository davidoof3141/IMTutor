# itm-tutor backend

Deterministic control layer + LLM tutor backend. See `/claude.md` at the repo
root for the full spec.

## Setup

```
uv sync
cp .env.example .env   # then fill in OPENROUTER_API_KEY
uv run python scripts/build_book_index.py   # builds the book RAG index in Postgres (needs OPENROUTER_API_KEY, makes embedding API calls)
uv run python scripts/extract_book_images.py   # extracts book figures for the tutor to display (one-time, local, no API key)
uv run python scripts/generate_chapter_intros.py   # pre-generates chapter/section welcome messages (needs OPENROUTER_API_KEY, makes real LLM calls)
```

## Deploying

Vercel's Python runtime installs from `requirements.txt`, not `pyproject.toml`/`uv.lock` directly. Regenerate it whenever dependencies change:

```
uv lock
uv export --no-dev --no-hashes --format requirements-txt -o requirements.txt
```

## Run

```
uv run uvicorn app.main:app --reload
```

## Test

```
uv run pytest
uv run ruff check .
uv run mypy app
```
