import asyncio
import json
import re
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from rag_engine import (
    get_retriever, get_vectorstore, extract_curriculum_from_pdf,
    get_chunks_for_subchapter, get_chunks_in_page_range, get_text_for_page_range,
    render_page_as_png, get_figures_in_page_range, get_figure_image,
    build_figure_index, render_figure_region, PDF_PATH,
)
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

app = FastAPI(
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0.2)

retriever = None
curriculum = None
figure_index = {}   # { "3.1": {"page": N, "caption": "Abb. 3.1 ..."} }


@app.on_event("startup")
async def startup_event():
    global retriever, curriculum, figure_index
    retriever = get_retriever()
    curriculum = extract_curriculum_from_pdf()
    figure_index = build_figure_index()
    print(f"Figure index built: {len(figure_index)} figures indexed.")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    chatType: str
    targetId: str | None = None
    preferences: dict
    learnerState: dict | None = None

class ChapterIntroRequest(BaseModel):
    targetId: str
    preferences: dict

class StepContentRequest(BaseModel):
    subId: str          # e.g. "ch3.1.1" or "ch3.1"
    stepTitle: str | None = None
    preferences: dict


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _learner_profile_block(p: dict) -> str:
    return f"""## Learner Profile
- Role: {p.get('role', 'Other')}
- IS/IT expertise: {p.get('globalCompetency', 'intermediate')}
- Industry: {p.get('industry', 'IT/Tech')}
- Organisation size: {p.get('orgSize', 'Enterprise')}
- Learning goal: {p.get('learningGoal', 'practical')}
- Time per session: {p.get('timeAvailability', 'standard')}
- Learning style: {p.get('learnerType', 'reading')}
- Language preference: {p.get('languagePreference', 'bilingual')}
- Tone: {p.get('tone', 'professional')}
- Format: {p.get('format', 'standard')}"""


def _extract_figures_from_text(text: str) -> list[dict]:
    """
    Find all 'Abb. X.Y' references in text, look them up in the figure index,
    and return a deduplicated list of figure metadata for the frontend.
    """
    refs_found = re.findall(r"Abb\.\s*(\d+\.\d+)", text)
    seen = set()
    result = []
    for ref in refs_found:
        if ref in seen:
            continue
        seen.add(ref)
        if ref in figure_index:
            entry = figure_index[ref]
            result.append({
                "ref": f"Abb. {ref}",
                "ref_key": ref,
                "page": entry["page"],
                "caption": entry["caption"],
                "xref": entry.get("xref"),
            })
    return result


_PAGE_REF_INSTRUCTION = (
    "\n## References — IMPORTANT\n"
    "1. **Page references**: when citing textbook content embed an inline badge using EXACTLY "
    "this format: [p. X](#page-X) where X is the page number. "
    "Example: 'Stachowiak defines a model as a shortened image [p. 3](#page-3).'\n"
    "2. **Figure references**: whenever a concept is illustrated by a figure in the textbook, "
    "mention it by name inline — e.g. 'As shown in Abb. 3.1, ...' or 'Abb. 3.4 illustrates ...'. "
    "Use the exact notation 'Abb. X.Y' so figures can be displayed automatically.\n"
    "Place all references naturally in context — do NOT group them at the end.\n"
)


def _get_subchapter_info(target_id: str):
    """Returns (title, sub_subchapters_list) for a given subchapter id."""
    if not curriculum:
        return target_id, []
    for ch in curriculum.get("chapters", []):
        for sub in ch.get("subchapters", []):
            if sub["id"] == target_id:
                return sub["title"], sub.get("subchapters", [])
    return target_id, []


def _get_page_range(section_id: str) -> tuple[int | None, int | None]:
    """Return (start_page, end_page) for any section id from curriculum."""
    if not curriculum:
        return None, None
    for ch in curriculum.get("chapters", []):
        for sub in ch.get("subchapters", []):
            if sub["id"] == section_id:
                return sub.get("start_page"), sub.get("end_page")
            for ss in sub.get("subchapters", []):
                if ss["id"] == section_id:
                    return ss.get("start_page"), ss.get("end_page")
    return None, None


def _find_curriculum_sections_for_pages(page_refs: list) -> list[dict]:
    """Return curriculum subchapters whose page range overlaps with the given page list."""
    if not curriculum or not page_refs:
        return []
    page_set = set(page_refs)
    matches = []
    seen: set = set()
    for ch in curriculum.get("chapters", []):
        for sub in ch.get("subchapters", []):
            start = sub.get("start_page")
            end = sub.get("end_page")
            if start and end and sub["id"] not in seen:
                if set(range(start, end + 1)) & page_set:
                    matches.append({"id": sub["id"], "title": sub["title"]})
                    seen.add(sub["id"])
    return matches


def _get_steps_for_subchapter(target_id: str) -> list[dict]:
    """Steps = sub-subchapters if present, else single step = the subchapter itself."""
    _, sub_subchapters = _get_subchapter_info(target_id)
    if sub_subchapters:
        return [
            {"index": i, "title": ss["title"], "subId": ss["id"]}
            for i, ss in enumerate(sub_subchapters)
        ]
    title, _ = _get_subchapter_info(target_id)
    return [{"index": 0, "title": title, "subId": target_id}]


async def _generate_suggestions(topic: str, context_hint: str) -> list[str]:
    """Fast parallel call to generate 3 follow-up prompt suggestions."""
    messages = [
        SystemMessage(content=(
            f"You generate follow-up learning prompts for a student studying '{topic}'. "
            "Return ONLY a valid JSON array of exactly 3 short strings (questions or next actions). "
            "No markdown, no extra text — just the JSON array."
        )),
        HumanMessage(content=f"Context: {context_hint[:400]}\n\nGenerate 3 follow-up suggestions:"),
    ]
    try:
        result = await llm.ainvoke(messages)
        # Strip any accidental markdown fences
        raw = result.content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        suggestions = json.loads(raw)
        if isinstance(suggestions, list):
            return [str(s) for s in suggestions[:3]]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/curriculum")
def get_curriculum():
    global curriculum
    if curriculum is None:
        curriculum = extract_curriculum_from_pdf()
    return curriculum


@app.get("/api/pdf")
def serve_pdf():
    """Serve the raw PDF for the frontend PDF viewer."""
    return FileResponse(PDF_PATH, media_type="application/pdf", filename="textbook.pdf")


@app.get("/api/page-image/{page_number}")
def get_page_image(page_number: int):
    try:
        png_bytes = render_page_as_png(page_number)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found: {e}")


@app.get("/api/figure/{xref}")
def get_figure(xref: int):
    try:
        img_bytes = get_figure_image(xref)
        return Response(content=img_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Figure xref {xref} not found: {e}")


@app.get("/api/figure-ref/{ref_key}")
def get_figure_by_reference(ref_key: str):
    entry = figure_index.get(ref_key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Figure {ref_key} not found")

    try:
        # If the figure is an embedded image, return the raw image directly.
        if entry.get("xref"):
            img_bytes = get_figure_image(entry["xref"])
            return Response(content=img_bytes, media_type="image/jpeg")

        png_bytes = render_figure_region(
            entry["page"],
            ref_key=ref_key,
            caption=entry.get("caption"),
        )
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Figure {ref_key} not found: {e}")


@app.post("/api/chapter-summary")
async def chapter_summary_endpoint(req: ChapterIntroRequest):
    subchapter_title, _ = _get_subchapter_info(req.targetId)
    start_page, end_page = _get_page_range(req.targetId)

    if start_page and end_page:
        context_text = get_text_for_page_range(start_page, end_page)
        page_range_str = f"pages {start_page}–{end_page}"
    else:
        docs = get_chunks_for_subchapter(req.targetId)
        context_text = "\n\n".join([doc.page_content for doc in docs])
        page_range_str = "the relevant pages"

    safe_context = context_text.replace("{", "{{").replace("}", "}}")
    profile = _learner_profile_block(req.preferences).replace("{", "{{").replace("}", "}}")

    system = f"""You are an expert AI tutor for Information Systems based on Krcmar's textbook.

{profile}

Write a clear, engaging overview (3–4 paragraphs) of "{subchapter_title}" ({page_range_str}).
Base your answer EXCLUSIVELY on the textbook content provided below — do not add concepts from other chapters or external sources.
Cover: what this topic is about, the core concepts, why it matters for IS practice, and how it connects to the broader chapter.
Adapt language, depth, and examples to the learner profile above.
Do not use a heading — start directly with the content.
{_PAGE_REF_INSTRUCTION}
### Textbook Content ({page_range_str})
{safe_context}
"""
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", "{question}")])
    chain = prompt | llm | StrOutputParser()

    response_text, suggestions = await asyncio.gather(
        chain.ainvoke({"question": f"Give me an overview of {subchapter_title}."}),
        _generate_suggestions(subchapter_title, f"Overview of {subchapter_title}"),
    )
    figures = _extract_figures_from_text(response_text)
    return {"text": response_text, "suggestions": suggestions, "figures": figures, "kcs": []}


@app.post("/api/learning-plan")
async def learning_plan_endpoint(req: ChapterIntroRequest):
    subchapter_title, sub_subchapters = _get_subchapter_info(req.targetId)
    steps = _get_steps_for_subchapter(req.targetId)
    start_page, end_page = _get_page_range(req.targetId)

    if start_page and end_page:
        context_text = get_text_for_page_range(start_page, end_page)
        page_range_str = f"pages {start_page}–{end_page}"
    else:
        docs = get_chunks_for_subchapter(req.targetId)
        context_text = "\n\n".join([doc.page_content for doc in docs])
        page_range_str = "the relevant pages"

    safe_context = context_text.replace("{", "{{").replace("}", "}}")
    profile = _learner_profile_block(req.preferences).replace("{", "{{").replace("}", "}}")
    p = req.preferences

    # Build section structure + step count constraint
    if sub_subchapters:
        num_steps = len(sub_subchapters)
        section_lines = []
        for i, ss in enumerate(sub_subchapters):
            ss_start, ss_end = _get_page_range(ss["id"])
            page_hint = f" (pages {ss_start}–{ss_end})" if ss_start and ss_end else ""
            section_lines.append(f"- Step {i+1} → {ss['title']}{page_hint}")
        section_block = (
            f"\n## Required Plan Structure\n"
            f"This subchapter has exactly {num_steps} sections. "
            f"Create EXACTLY {num_steps} steps, one per section:\n"
            + "\n".join(section_lines) + "\n"
        )
    else:
        num_steps = "3 to 5"
        section_block = (
            f"\n## Required Plan Structure\n"
            f"Create a concise plan with 3 to 5 steps covering the key concepts in this subchapter.\n"
        )

    system = f"""You are an expert AI tutor for Information Systems based on Krcmar's textbook.

{profile}

## Scope — CRITICAL
You are creating a learning plan ONLY for the subchapter "{subchapter_title}" ({page_range_str}).
This is ONE subchapter — NOT the entire chapter. Do NOT reference or include content from any other subchapters.
{section_block}
## Chapter Context
- Topic familiarity: {p.get('topicFamiliarity', 'new')}
- Relevance to current work: {p.get('relevance', 'general')}
- Focus area: {p.get('specificInterest', 'entire')}
- Confidence goal: {p.get('confidenceLevel', 'deep')}

Create exactly {num_steps} steps. Keep the ENTIRE plan SHORT — aim for roughly 150 words per step.
For each step provide ONLY:
1. **Title** — the section heading
2. **Covers** — 1–2 sentences on what the learner will understand, with page reference
3. **Activity** — one short sentence suggesting a single activity for a {p.get('learnerType', 'reading')}-style learner
4. **Time** — estimated minutes for a {p.get('timeAvailability', 'standard')} session

Do NOT include sub-bullets, detailed reading lists, figure-by-figure breakdowns, or summary sections. Be brief and encouraging.
{_PAGE_REF_INSTRUCTION}
### Textbook Content ({page_range_str})
{safe_context}
"""
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", "{question}")])
    chain = prompt | llm | StrOutputParser()

    response_text, suggestions = await asyncio.gather(
        chain.ainvoke({"question": f"Create my personalised learning plan for {subchapter_title}."}),
        _generate_suggestions(subchapter_title, f"Learning plan for {subchapter_title}"),
    )
    return {"text": response_text, "steps": steps, "suggestions": suggestions, "kcs": []}


@app.post("/api/step-content")
async def step_content_endpoint(req: StepContentRequest):
    step_title = req.stepTitle or req.subId
    start_page, end_page = _get_page_range(req.subId)

    if start_page and end_page:
        docs = get_chunks_in_page_range(start_page, end_page)
    else:
        docs = get_chunks_for_subchapter(req.subId)

    if not docs:
        docs = get_vectorstore().similarity_search(step_title, k=8)

    context_text = "\n\n".join([doc.page_content for doc in docs])
    safe_context = context_text.replace("{", "{{").replace("}", "}}")
    page_refs = sorted({d.metadata.get("page_number") for d in docs if d.metadata.get("page_number")})
    profile = _learner_profile_block(req.preferences).replace("{", "{{").replace("}", "}}")
    p = req.preferences

    page_range_str = f"pages {page_refs[0]}–{page_refs[-1]}" if len(page_refs) > 1 else f"page {page_refs[0]}" if page_refs else "relevant pages"

    system = f"""You are an expert AI tutor for Information Systems based on Krcmar's textbook.

{profile}

## Learning Step
Guide the learner through: "{step_title}" ({page_range_str} of the textbook).

Structure your response as follows:
1. **What this covers** — one sentence framing the topic.
2. **Core concepts** — explain the key ideas clearly, with concrete examples from the {p.get('industry', 'IT/Tech')} industry.
3. **Key terms** — define 2–4 important terms from this section.
4. **Textbook reference** — mention specific concepts from the provided content and the page range ({page_range_str}).
5. **Check your understanding** — pose 1 reflective question the learner can answer to themselves.

Adjust depth for {p.get('timeAvailability', 'standard')} sessions and {p.get('globalCompetency', 'intermediate')} expertise.
Tone: {p.get('tone', 'professional')}. Format: {p.get('format', 'standard')}.
{_PAGE_REF_INSTRUCTION}
### Textbook Content ({page_range_str})
{safe_context}
"""
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", "{question}")])
    chain = prompt | llm | StrOutputParser()

    response_text, suggestions = await asyncio.gather(
        chain.ainvoke({"question": f"Guide me through: {step_title}"}),
        _generate_suggestions(step_title, f"Step guide for {step_title}"),
    )
    figures = _extract_figures_from_text(response_text)
    return {"text": response_text, "page_refs": page_refs, "figures": figures, "suggestions": suggestions, "kcs": []}


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    global retriever

    if retriever is None:
        raise HTTPException(status_code=503, detail="Retriever is not ready yet.")

    if req.chatType == "subchapter" and req.targetId:
        # Restrict context strictly to this subchapter's pages
        start_page, end_page = _get_page_range(req.targetId)
        if start_page and end_page:
            context_text = get_text_for_page_range(start_page, end_page)
            page_refs = list(range(start_page, end_page + 1))
        else:
            docs = get_chunks_for_subchapter(req.targetId)
            context_text = "\n\n".join([doc.page_content for doc in docs])
            page_refs = sorted({d.metadata.get("page_number") for d in docs if d.metadata.get("page_number")})
    else:
        docs = retriever.invoke(req.message)
        context_text = "\n\n".join([doc.page_content for doc in docs])
        page_refs = sorted({d.metadata.get("page_number") for d in docs if d.metadata.get("page_number")})

    safe_context = context_text.replace("{", "{{").replace("}", "}}")
    safe_learner_state = str(req.learnerState).replace("{", "{{").replace("}", "}}")

    p = req.preferences
    profile = _learner_profile_block(p)

    system_instruction = f"""You are an expert AI tutor for Information Systems based on Krcmar's textbook.

{profile}

Adapt your explanations to the learner's industry ({p.get('industry', 'IT/Tech')}), expertise ({p.get('globalCompetency', 'intermediate')}), and time availability ({p.get('timeAvailability', 'standard')}).
"""

    if req.chatType == "subchapter":
        subchapter_title, _ = _get_subchapter_info(req.targetId)
        start_page, end_page = _get_page_range(req.targetId)
        page_range_str = f"pages {start_page}–{end_page}" if start_page and end_page else "the relevant pages"
        system_instruction += f"""
## Chapter Context
You are in structured teaching mode for: **{subchapter_title}** ({page_range_str}).
- Topic familiarity: {p.get('topicFamiliarity', 'new')}
- Relevance to current work: {p.get('relevance', 'general')}
- Focus area: {p.get('specificInterest', 'entire')}
- Confidence goal: {p.get('confidenceLevel', 'deep')}

Learner's current Merill state: {safe_learner_state}.
Follow Merrill's First Principles of Instruction.
Answer ONLY using the textbook content below ({page_range_str}). Do not introduce concepts from other chapters.
"""
        system_instruction += _PAGE_REF_INSTRUCTION
    else:
        system_instruction += "\nYou are in General Chat Mode. Answer freely, drawing on the textbook when relevant.\n"
        system_instruction += _PAGE_REF_INSTRUCTION

    system_instruction += f"\n### Textbook Context\n{safe_context}\n"

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_instruction),
        ("human", "{question}"),
    ])
    chain = prompt | llm | StrOutputParser()

    topic = req.targetId or "Information Systems"
    response_text, suggestions = await asyncio.gather(
        chain.ainvoke({"question": req.message}),
        _generate_suggestions(topic, req.message),
    )

    figures = _extract_figures_from_text(response_text)
    curriculum_matches = (
        _find_curriculum_sections_for_pages(page_refs)
        if req.chatType != "subchapter"
        else []
    )

    return {
        "text": response_text,
        "page_refs": page_refs,
        "figures": figures,
        "suggestions": suggestions,
        "kcs": ["Extracted from Textbook"],
        "intent": "content_request",
        "curriculum_matches": curriculum_matches,
    }


@app.get("/api")
def api_root_info():
    return {
        "message": "API root",
        "openapi": "/api/openapi.json",
        "docs": "/api/docs",
        "redoc": "/api/redoc",
    }


@app.get("/api/debug/chunks")
def debug_chunks(limit: int = Query(default=10, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    vectorstore = get_vectorstore()
    all_ids = list(vectorstore.docstore._dict.keys())
    selected_ids = all_ids[offset:offset + limit]
    chunks = []
    for idx, doc_id in enumerate(selected_ids, start=offset + 1):
        doc = vectorstore.docstore._dict[doc_id]
        chunks.append({
            "index": idx,
            "doc_id": doc_id,
            "metadata": doc.metadata,
            "length": len(doc.page_content),
            "preview": doc.page_content[:500],
        })
    return {"total_chunks": len(all_ids), "offset": offset, "returned": len(chunks), "chunks": chunks}


@app.get("/api/debug/retrieve")
def debug_retrieve(query: str = Query(..., min_length=2), k: int = Query(default=4, ge=1, le=20)):
    vectorstore = get_vectorstore()
    docs = vectorstore.similarity_search(query, k=k)
    return {
        "query": query,
        "k": k,
        "results": [
            {"rank": i, "metadata": doc.metadata, "length": len(doc.page_content), "preview": doc.page_content[:500]}
            for i, doc in enumerate(docs, start=1)
        ],
    }
