
# CLAUDE.md — Adaptive tutoring prototype

## What this is

A tutoring web app with a **deterministic control layer** between the learner
profile and the language model. The learner answers a short onboarding
questionnaire once; a rule engine maps those answers to six didactic
parameters; those parameters select fixed prompt clauses that configure an LLM
tutor. The learner can see the rules that produced their configuration and
override any parameter.

This is a research prototype for a master's thesis. The point of the system is
the control layer's **auditability**, not tutoring quality. Design decisions
that improve tutoring at the cost of predictability are wrong here.

## Hard invariants

These are requirements, not preferences. Each must be enforced in code and
covered by a test. If a feature request conflicts with one of these, stop and
raise it rather than working around it.

1. **The mapping function is pure.** No network, no clock, no randomness, no
   file I/O at call time, no global state. Same profile in, same vector out,
   forever.
2. **The mapping function is total.** Every combination of admissible profile
   values returns a fully populated control vector. There is no "unknown"
   branch and no fallback to model judgement.
3. **No LLM anywhere in the mapping path.** `core/mapping.py` and
   `core/rules.py` must not import the LLM client, directly or transitively.
   Enforce with an import test.
4. **Every parameter value is attributable.** The mapper returns
   `(vector, attribution)` where attribution maps each of the six parameters
   to the rule id that set it, or to `"default"`.
5. **Overrides never mutate the derived vector.** Overrides are a sparse dict
   applied over the derived vector to produce the effective vector. The
   derived vector must remain recoverable at all times.
6. **No feedback from dialogue to profile or configuration.** Nothing the
   learner says or scores changes the profile, the rules, or the vector. Quiz
   results are logged and otherwise ignored by the control layer.
7. **The rule set is data, not code.** Rules live in versioned YAML. Adding a
   rule must never require a Python change.

Note on scope: determinism is a property of the **control layer**, not of the
generated text. The LLM is stochastic. Never claim otherwise in code comments
or UI copy.

## Data model

```python
Role            = Literal["practitioner", "analyst", "academic"]
PriorExperience = Literal["none", "low", "moderate", "high"]
Goal            = Literal["certification", "applied_competence", "orientation"]
StudyTime       = Literal["under_2h", "2_to_4h", "over_4h"]

class Profile(BaseModel):        # immutable
    learner_id: str
    role: Role
    prior_experience: PriorExperience
    goal: Goal
    study_time: StudyTime
    ruleset_version: str         # pinned at onboarding
    created_at: datetime

class ControlVector(BaseModel):
    explanation_depth: int       # 1-5
    example_density: int         # 1-5
    concreteness: int            # 1-5
    register: Literal["formal", "neutral", "informal"]
    pacing: int                  # topics per week, 1-3
    assessment_frequency: Literal["every_topic", "every_second_topic", "on_request"]

Attribution = dict[str, str]     # parameter name -> rule id or "default"
Override    = dict[str, Any]     # sparse; keys are ControlVector fields
```

`Profile` is write-once. Changing circumstances means re-onboarding, which
creates a new profile record — never an in-place update.

`ruleset_version` is pinned on the profile so a past session's configuration
stays reproducible after the rules change.

## Core contracts

```python
def derive(profile: Profile, ruleset: RuleSet) -> tuple[ControlVector, Attribution]
def effective(derived: ControlVector, override: Override) -> ControlVector
def assemble(vector: ControlVector, catalogue: ClauseCatalogue) -> str
```

`derive` evaluates rules in declared priority order. Where two rules write the
same parameter, the higher priority wins and the attribution records the
winner. Parameters no rule touches take the catalogue default.

`assemble` performs selection and concatenation only. It must not generate,
paraphrase, or template-interpolate free text. Output is
`base_instruction + "\n" + one clause per parameter`, in declared order.

## Rule and clause files

`rules/ruleset.v1.yaml`:

```yaml
version: v1
defaults:
  explanation_depth: 3
  example_density: 3
  concreteness: 3
  register: neutral
  pacing: 2
  assessment_frequency: every_second_topic
rules:
  - id: exp_low
    priority: 10
    when: { prior_experience: [none, low] }
    set: { explanation_depth: 4, example_density: 4 }
  - id: role_practitioner
    priority: 10
    when: { role: practitioner }
    set: { concreteness: 4, register: informal }
```

`rules/clauses.v1.yaml` maps every admissible value of every parameter to
exactly one fixed sentence. A missing entry is a startup error, not a runtime
fallback. Written in German, with an explicit "respond only in German"
sentence in `base_instruction` -- the tutor's output language is a product
requirement, not left to the surrounding context to imply. Every other fixed
string a turn can send to the model (`format_focus`, `format_overview`,
`format_context`'s wrapper line, the lesson step templates, the chapter-intro
instruction) is German for the same reason.

## Layout

```
backend/
  app/
    main.py
    api/          routes only, no logic
    core/         profile.py rules.py mapping.py clauses.py assembler.py
                  planner.py step_templates.py  (lesson planning)
    llm/          client.py  (OpenRouter)
    rag/          chunking.py index.py retriever.py toc.py  (book RAG + curriculum)
                  images.py book_images.py  (book figure extraction + lookup)
    store/        repositories, incl. lessons.py
    logging/      session and turn logs
  scripts/        build_book_index.py extract_book_images.py
  rules/          ruleset.v1.yaml clauses.v1.yaml planner.v1.yaml step_templates.v1.yaml
  tests/
frontend/
  src/            onboarding, tutor chat, scrutability panel, mode toggle, curriculum,
                  lesson step rail, history
```

`core/` is the thesis contribution and must be usable as a library without
FastAPI. Keep framework imports out of it.

## API

```
POST   /api/onboarding                    -> profile, derived vector, attribution
GET    /api/config/{learner_id}           -> derived, override, effective, attribution
PUT    /api/config/{learner_id}/override  -> set one or more parameters
DELETE /api/config/{learner_id}/override/{param}   -> revert one parameter
DELETE /api/config/{learner_id}/override  -> reset to derived
GET    /api/rules?version=v1              -> the full rule set and clause catalogue
POST   /api/chat/{learner_id}             -> one tutoring turn (optional conversation_id)
POST   /api/chat/{learner_id}/suggestions -> three follow-up question chips for a thread
GET    /api/conversations/{learner_id}                       -> the learner's threads
POST   /api/conversations/{learner_id}                       -> start an empty thread
GET    /api/conversations/{learner_id}/{id}/messages         -> one thread's messages
GET    /api/book-images/{image_id}        -> one extracted book figure's bytes
GET    /api/book/pdf                      -> the textbook PDF (for reference links)
GET    /api/planner?version=v1            -> the full planner table and step templates
POST   /api/lesson/{learner_id}           -> plan a lesson for the current training-mode
                                              selection and run its first step
GET    /api/lesson/{conversation_id}      -> plan, rationale, current_step, vector_drifted
POST   /api/lesson/{conversation_id}/advance   -> run the next step
POST   /api/lesson/{conversation_id}/abandon   -> mark abandoned, keep the row
GET    /api/export/{learner_id}           -> full interaction log
```

`GET /api/rules` is not a debug endpoint. Publishing the rule set is a thesis
requirement — a third party must be able to reproduce any learner's
configuration without running the system. `GET /api/planner` exists for the
same reason, for the planner table a lesson plan is built from.

## Frontend

Three surfaces:

- **Onboarding** — four closed questions, no free text. Free text would need
  interpreting and would break invariant 1.
- **Tutor chat** — ordinary chat against the configured model. Replies that
  drew on book passages show the source figures inline and a row of page
  reference chips; clicking one opens the textbook PDF in an in-app modal
  jumped to that page.
- **Scrutability panel** — the important one. Shows, in this order: the
  profile as answered; the rules that fired with their ids; the derived
  vector; the effective vector with overrides marked; per-parameter revert and
  a global reset. Showing settings alone is not sufficient — the derivation is
  the point. A fourth block, when the active thread has a lesson: the plan's
  steps with their rationale, and a drift banner when `vector_drifted`.
- **Lesson step rail** (training mode) — the full plan up front, current step
  marked, completed steps checked; rationale on expand ("Erklärung 2 von 4 —
  explanation_depth = 4"). Primary action is "Weiter" (advance); free text in
  the thread is an ordinary tutoring turn and never moves the pointer. A
  completed lesson shows "Lektion abgeschlossen"; an abandoned one stays
  visible but inert.

## LLM integration

OpenRouter, OpenAI-compatible client, `base_url="https://openrouter.ai/api/v1"`,
key from `OPENROUTER_API_KEY`. Never hardcode keys.

Pin the model per session and record the id in the profile and every turn log —
a session's configuration is not reproducible if the model silently changes.
Expose `temperature` in config, default `0.7` for tutoring, and use `0.0` for
the parameter manipulation-check harness.

## Book RAG

The course textbook (`backend/Krcmar2015_Informationsmanagement.pdf`) is
indexed as a local Chroma vector store (`backend/data/chroma/`, rebuilt via
`uv run python scripts/build_book_index.py`) using a local multilingual
sentence-transformers model — no embedding API calls, no extra key.

Each chat turn embeds the learner's message, retrieves the top-k book chunks,
and passes them to the model as their own system message (see
`app/llm/client.py::complete_turn`'s `book_context` parameter). Retrieved text
is never mixed into `core/assembler.py`'s output — `assemble()` stays pure
clause selection/concatenation, so the scrutability panel keeps showing
exactly the assembled system prompt with nothing else folded in. The
retrieved context is logged verbatim per turn (`book_context` in the turn
log) alongside the prompt and completion, for the same reproducibility reason
everything else in the turn log is verbatim.

Retrieval is best-effort: if the index hasn't been built yet, `retrieve()`
returns no chunks and chat proceeds without book grounding rather than
failing the turn.

## Book figures and page references

The book's figures are extracted offline into `backend/data/book_images/`
(rebuilt via `uv run python scripts/extract_book_images.py`) so the tutor can
show them alongside a reply, and every reply can link back to the pages it
drew on. Two extraction passes, both in `app/rag/images.py`:

- `extract_images` — embedded raster images (photos/scans) via `pypdf`,
  filtered to drop decorative artifacts (`MIN_DIMENSION`).
- `extract_vector_figures` — most of this book's diagrams are drawn as PDF
  vector paths, not embedded images, so `pypdf` can't see them. This pass
  uses PyMuPDF to cluster a page's drawing operators (a diagram's
  boxes/arrows/sub-panels sit close together; running text draws no paths at
  all) and rasterizes each cluster's bounding box. It's a geometric
  heuristic, not true figure detection — tuned against a sample of pages, it
  can occasionally crop a table's grid lines or merge two nearby figures.

Both passes write into one manifest (`app/rag/book_images.py::load_manifest`),
looked up read-only at chat time by page number.

Each chat turn (`app/api/chat.py`) reuses the same `retrieve()` call already
made for book RAG context to derive, independent of whether the model's
prose actually cites them:

- `book_images` — figures on the retrieved pages (`images_for_pages`), capped
  and served from `GET /api/book-images/{id}`.
- `reference_pages` — the retrieved pages themselves, deduped, relevance-
  ordered.

Both are returned via response headers (`X-Book-Image-Ids`,
`X-Book-Reference-Pages`) for the turn just streamed, and persisted against
the tutor's message (`message_book_images`, `message_page_refs` tables) so
they replay with conversation history — same "best-effort, degrades
gracefully" spirit as book RAG: an unbuilt manifest just means no figures.

`GET /api/book/pdf` serves the textbook PDF itself; the frontend fetches it
once, caches the blob URL for the tab, and opens `<url>#page=N` in a modal
when a reference chip is clicked.

## Study mode and curriculum

Two modes, chosen per learner and persisted in SQLite
(`app/store/study_mode.py`, defaults to `exploration`): **exploration**
(plain chat, today's behavior) and **training**, where the learner picks a
chapter (and optionally a section) from a schedule.

The schedule is extracted automatically from the book's own PDF outline
(`app/rag/toc.py::extract_curriculum`, run once at server startup — it's
cheap, no embeddings involved) into chapters with their `X.Y` subsections and
page ranges. `GET /api/curriculum` serves it; `GET`/`PUT /api/mode/{learner_id}`
read and set the learner's mode/selection.

Training mode is a **soft** focus, not a hard filter: book retrieval
(`app/rag/retriever.py::retrieve`) still searches the whole book. Selecting a
chapter only adds a fixed-template system message
(`app/rag/toc.py::format_focus`) naming what the learner is studying — same
boundary as book RAG context, kept out of `core/assembler.py`'s pure output
and passed to `complete_turn` via the existing `book_context` parameter. Mode
selection never touches the control vector or the mapping invariants.

### Chapter intro

A short welcome message for training mode's chapter/section selection: an
overview plus how it fits into the book's structure (grounded in a real
table of contents via `app/rag/toc.py::format_overview`, not the model
inventing one). **Pre-generated and static**, not a live call per request —
one fixed text per chapter and per section, the same for every learner. That
trades away this one message's usual per-learner style adaptation
(`assemble()`) for zero request-time cost/latency and full reproducibility,
which fits this project's ethos better than a live, stochastic call would.

`scripts/generate_chapter_intros.py` builds `backend/data/chapter_intros.json`
(gitignored/rebuildable, same as the book index and figures) by calling
`complete_turn` once per chapter/section, styled with the *ruleset's default*
vector (no rule fired, no override — the neutral baseline, since there's no
per-learner vector to use here). Unlike the other build scripts it needs
`OPENROUTER_API_KEY` and costs real tokens; rerun it after the book, the
curriculum, or `clauses.v1.yaml`'s wording changes. `GET
/api/chapter-intro/{learner_id}` (`app/api/chapter_intro.py`) is then a plain
manifest lookup keyed by `chapter_number` (or `chapter_number:section_number`)
— no model call, no conversation, no message row, so it never appears in
conversation history and never touches the turn log either (it isn't a model
*turn* for this learner, just a static read). A missing manifest entry is a
404, not a fallback live generation.

The frontend (`ChatPanel`) re-fetches this every time the training-mode
selection changes and shows it only while the current thread has zero real
messages; the moment the learner sends one, the preview is discarded and the
ordinary `/api/chat` path takes over. It is intentionally a separate concept
from a lesson's step-0 message (below) — starting a lesson already produces a
real, persisted introductory turn, so by the time a lesson exists this
preview's "thread is still empty" condition no longer holds.

## Lesson plans

A lesson plan sits beside the control layer and consumes its output; it
gives training mode a workflow and makes `pacing`/`assessment_frequency`
observable (the catalogue clauses for those two had no consuming mechanism
before this). Same purity bar as the control layer:

```python
def plan_lesson(
    vector: ControlVector,
    selection: CurriculumSelection,
    curriculum: Curriculum,
    table: PlannerTable,
) -> tuple[list[LessonStep], PlanRationale]
```

`app/core/planner.py` — pure, total, deterministic, no I/O at call time, no
LLM import (`tests/test_purity.py` extends its import check to this file).
The plan does **not** change based on how the learner performs: no
remediation, no skipping, no difficulty adjustment — checkpoint answers are
ordinary chat turns, logged and otherwise ignored (invariant 6 extended to
this layer). The numbers a plan is built from live in `rules/planner.v1.yaml`
(same reasoning as invariant 7): section count per `pacing`, explain/example
beats per section per `explanation_depth`/`example_density`, and a
checkpoint placement pattern per `assessment_frequency`. What those numbers
*mean* — how they turn into a step sequence — is `plan_lesson`'s job, not the
YAML's.

`lesson_id` and `created_at` are assigned by the caller (`app/api/lesson.py`),
not the planner — `datetime` can't be imported into `core/planner.py` at all
under the purity test, not even for a type annotation, so `LessonPlan` (the
full plan: the planner's steps plus that identity/timestamp) lives in
`app/store/lessons.py` instead.

**Rationale**, same spirit as `Attribution` in the mapping layer: a
`step_index -> "parameter=value"` dict alongside the steps (`recap` always
attributes to `"always"`). `pacing`'s applicability is recoverable from
`section_ref` on the plan itself (`None` = whole chapter, pacing applied;
set = one specific section, pacing had nothing to select over) rather than a
synthetic rationale entry of its own.

**Step templates** (`rules/step_templates.v1.yaml`, `app/core/step_templates.py`)
are one fixed instruction sentence per `StepKind`, same totality-at-load-time
rule as the clause catalogue. `format_step` substitutes only `section_ref`,
`page_start`, `page_end` — no other interpolation, same spirit as
`app/rag/toc.py::format_focus`. A step's turn passes this, plus the existing
training-mode focus message, via `book_context` — never folded into
`core/assembler.py`'s output, so the scrutability panel keeps showing exactly
the assembled system prompt.

**Execution**: `POST /api/lesson/{learner_id}` plans a lesson for the
learner's current training-mode selection, creates a conversation, and runs
step 0 as a server-initiated turn (`app/store/conversations.py::add_tutor_message`
— a tutor message with no paired learner message, since nothing was typed).
`POST /api/lesson/{conversation_id}/advance` runs the next step; free-text
messages in the thread go through the ordinary `/api/chat` path and never
move the pointer. A plan is immutable once created — `advance` only ever
moves `current_step` forward (flipping `status` to `completed` on the final
step) and never touches `steps`/`rationale`/`vector_snapshot`. If overrides
change mid-lesson the plan does not re-plan; `GET`/`advance`/`abandon`
responses carry `vector_drifted` (current effective vector vs.
`vector_snapshot`) so the frontend can flag it without the plan itself
changing.

## Conversation history

Chat is organised into **conversations** (threads), stored in Postgres
(`app/store/conversations.py`: a `conversations` row per thread, a `messages`
row per turn-half). Separate from the turn-log JSONL — that stays the
append-only evaluation dataset; this is the learner-facing store the sidebar
lists and resumes.

`POST /api/chat/{learner_id}` takes an optional `conversation_id`; a missing or
unknown one starts a fresh thread, and the id is returned in the
`X-Conversation-Id` response header. Resuming a thread replays its last
`MAX_HISTORY_MESSAGES` (20) turns to the model as ordinary user/assistant
messages, spliced in after the system + book-context messages and before the
new turn (`app/llm/client.py::_messages`, `history` param). A thread snapshots
the study mode it was started in, for the sidebar label only — a resumed turn
still uses the learner's *current* focus and retrieval.

New thread = explicit "Neues Gespräch" button in the frontend header (the row
is created lazily, on the first message). The history button opens a right
slide-over listing threads grouped by day; clicking one resumes it.

### Follow-up suggestion chips

Three clickable question chips above the input, so the learner can tap
instead of typing. Two sources, deliberately different:

- **Empty thread** — `STARTER_QUESTIONS` in `ChatPanel.tsx`, three fixed
  generic questions. Not chapter-specific and not fetched from anywhere;
  distinct from the pre-generated chapter intro above it.
- **After a reply** — `POST /api/chat/{learner_id}/suggestions`
  (`app/api/chat.py`) generates three fresh candidates from the conversation
  so far. Unlike the chapter intro this **can't** be pre-generated (it
  depends on what was just said), so it stays a live `complete_turn` call,
  triggered once the streamed reply finishes. Not persisted as a message,
  but logged to the turn log with the conversation's id, like the chapter
  intro was before it went static.

Clicking a chip sends that question immediately (`ChatPanel::sendMessage`,
factored out of the form's submit handler so both paths share it) rather
than just filling the input.

## Logging

Every turn writes: `learner_id`, `ruleset_version`, effective vector, sha256 of
the assembled system prompt, model id, temperature, prompt and completion,
token counts, `conversation_id`, timestamp. This is the evaluation dataset —
treat it as a deliverable, not as debug output.

Every turn also carries `lesson_id`, `step_index`, `step_kind` — all `null`
for an exploration-mode turn or a free-text turn in a lesson thread; set
together only when `app/api/lesson.py` drove that turn. Checkpoint answers
are logged as ordinary turns; there is no scoring field, and nothing reads
one back into the planner (invariant 6).

## Testing

Required, beyond ordinary unit tests:

- **Totality** — enumerate the full profile space (3 x 4 x 3 x 3 = 108) and
  assert `derive` returns a complete vector for every one.
- **Determinism** — call `derive` 100 times per profile, assert identical
  output.
- **Purity** — assert `core.mapping` and `core.rules` do not import
  `app.llm`, `httpx`, `requests`, `random`, or `datetime.now`.
- **Attribution completeness** — every parameter has a rule id or `"default"`.
- **Catalogue totality** — every admissible parameter value has exactly one
  clause; fail at startup otherwise.
- **Override isolation** — after any sequence of overrides and reverts, the
  derived vector is unchanged and reset returns the effective vector to it.
- **Golden prompts** — snapshot the assembled prompt for a fixed set of
  profiles so unintended wording changes surface in review.

For the lesson planner:

- **Planner totality** — for all 108 profiles x every chapter/section in the
  extracted curriculum, `plan_lesson` returns a non-empty, gap-free step list.
- **Planner determinism** — 100 calls per (profile, selection), identical
  output.
- **Rationale completeness** — every step has an attribution entry.
- **Parameter monotonicity** — raising `explanation_depth`/`example_density`/
  `pacing` never decreases the corresponding step/section count. Catches a
  planner-table edit that silently inverts a parameter's effect.
- **Template totality** — every `StepKind` has exactly one step template;
  fail at startup otherwise.
- **Plan immutability** — after any sequence of override changes and
  advances, the stored plan's steps and `vector_snapshot` stay
  byte-identical to creation.
- **No feedback** — a lesson driven with deliberately wrong checkpoint
  answers produces the same step list as one driven with correct ones. The
  invariant-6 regression test for this layer, made explicit.
- **Golden plans** — snapshot the full plan + rationale for a fixed set of
  (profile, selection) pairs, same reasoning as golden prompts.

## Conventions

- Python 3.11+, type hints everywhere, `pydantic` v2 models, `ruff` + `mypy`.
- No business logic in route handlers.
- Named constants over string literals for parameter names.
- Prefer boring, readable code over clever code — this gets read by an
  examiner, not just executed.