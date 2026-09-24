import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin_stats,
    attachments,
    auth,
    book_images,
    book_pdf,
    chapter_intro,
    chat,
    config,
    conversations,
    curriculum,
    export,
    health,
    lesson,
    onboarding,
    planner,
    rules,
    study_mode,
    users,
)
from app.api.deps import AppState
from app.core.clauses import ClauseCatalogue, load_catalogue
from app.core.planner import PlannerTable, load_planner_table
from app.core.rules import RuleSet, load_ruleset
from app.core.step_templates import StepTemplates, load_step_templates
from app.rag.chunking import BOOK_PATH
from app.rag.toc import extract_curriculum
from app.store import db

logger = logging.getLogger("app.main")

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"
RULESET_FILENAME = re.compile(r"^ruleset\.(?P<version>.+)\.yaml$")
PLANNER_FILENAME = re.compile(r"^planner\.(?P<version>.+)\.yaml$")
STEP_TEMPLATES_FILENAME = re.compile(r"^step_templates\.(?P<version>.+)\.yaml$")


def load_all_rulesets(
    rules_dir: Path,
) -> tuple[dict[str, RuleSet], dict[str, ClauseCatalogue]]:
    rulesets: dict[str, RuleSet] = {}
    catalogues: dict[str, ClauseCatalogue] = {}
    for ruleset_path in sorted(rules_dir.glob("ruleset.*.yaml")):
        match = RULESET_FILENAME.match(ruleset_path.name)
        if match is None:
            continue
        version = match.group("version")
        clauses_path = rules_dir / f"clauses.{version}.yaml"
        rulesets[version] = load_ruleset(ruleset_path)
        catalogues[version] = load_catalogue(clauses_path)
    return rulesets, catalogues


def load_all_planner_tables(
    rules_dir: Path,
) -> tuple[dict[str, PlannerTable], dict[str, StepTemplates]]:
    planner_tables: dict[str, PlannerTable] = {}
    for path in sorted(rules_dir.glob("planner.*.yaml")):
        match = PLANNER_FILENAME.match(path.name)
        if match is not None:
            planner_tables[match.group("version")] = load_planner_table(path)

    step_templates: dict[str, StepTemplates] = {}
    for path in sorted(rules_dir.glob("step_templates.*.yaml")):
        match = STEP_TEMPLATES_FILENAME.match(path.name)
        if match is not None:
            step_templates[match.group("version")] = load_step_templates(path)

    return planner_tables, step_templates


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    load_dotenv()
    rulesets, catalogues = load_all_rulesets(RULES_DIR)
    planner_tables, step_templates = load_all_planner_tables(RULES_DIR)
    # A serverless cold start can land while Neon's compute is still asleep or
    # while DATABASE_URL is misconfigured. Don't let that take the whole API
    # down -- log it and carry on; `db.ensure_schema()` retries on the first
    # request that reaches the database, and /api/health reports the state.
    try:
        db.init_db()  # create every table if missing
        db.seed_superuser()  # ensure the .env superuser exists
    except Exception:
        logger.exception("database unavailable at startup; deferring schema init")
    app.state.itm = AppState(
        rulesets=rulesets,
        catalogues=catalogues,
        curriculum=extract_curriculum(BOOK_PATH),
        planner_tables=planner_tables,
        step_templates=step_templates,
    )
    yield
    db.reset_pool()


app = FastAPI(title="itm-tutor", lifespan=lifespan)

_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Conversation-Id",
        "X-Book-Image-Ids",
        "X-Book-Reference-Pages",
        "X-Comparison-Id",
    ],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(onboarding.router)
app.include_router(config.router)
app.include_router(rules.router)
app.include_router(curriculum.router)
app.include_router(study_mode.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(attachments.router)
app.include_router(book_images.router)
app.include_router(book_pdf.router)
app.include_router(lesson.router)
app.include_router(planner.router)
app.include_router(chapter_intro.router)
app.include_router(export.router)
app.include_router(admin_stats.router)
