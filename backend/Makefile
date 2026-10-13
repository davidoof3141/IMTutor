# Offline maintenance tasks. Run from backend/ (needs `uv`, the Postgres book
# index, and -- for generation -- OPENROUTER_API_KEY in .env).

# Generate rapid diagnostics (Kalyuga & Sweller 2004) as static YAML under
# content/diagnostics/ for review and commit. Unchanged chapters are skipped.
#   make diagnostics                 all chapters
#   make diagnostics CHAPTER=4       one chapter
diagnostics:
	uv run python scripts/generate_diagnostics.py $(if $(CHAPTER),--chapter $(CHAPTER))

# Regenerate even if the stored source_hash still matches.
diagnostics-force:
	uv run python scripts/generate_diagnostics.py --force $(if $(CHAPTER),--chapter $(CHAPTER))

# List chapters whose diagnostic is missing or whose source_hash drifted.
diagnostics-stale:
	uv run python scripts/generate_diagnostics.py --stale

.PHONY: diagnostics diagnostics-force diagnostics-stale
