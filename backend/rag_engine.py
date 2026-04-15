import os
import re
from collections import Counter
import fitz # PyMuPDF
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

PDF_PATH = os.environ.get("PDF_PATH", "../Krcmar2015_ch3.pdf")
FAISS_INDEX_PATH = "faiss_index"

def _is_likely_heading_title(line: str) -> bool:
    if not line:
        return False
    if len(line) < 3 or len(line) > 90:
        return False
    if not re.search(r"[A-Za-zÄÖÜäöüß]", line):
        return False
    if re.match(r"^(Abb\.|Tab\.|DOI|©)", line):
        return False
    if line[0].islower():
        return False
    return True


def extract_curriculum_from_pdf():
    doc = fitz.open(PDF_PATH)
    total_pages = doc.page_count

    chapter_titles = {}
    chapter_counts = Counter()
    subchapter_titles = {}
    subchapter_counts = Counter()
    subsubchapter_titles = {}

    # First occurrence of each heading = start page (1-indexed)
    subchapter_start_page = {}    # (ch, sub) -> page
    subsubchapter_start_page = {} # (ch, sub, subsub) -> page

    for page_num in range(total_pages):
        lines = [line.strip() for line in doc.load_page(page_num).get_text().splitlines() if line.strip()]
        idx = 0
        while idx < len(lines) - 1:
            number_line = lines[idx]
            title_line = lines[idx + 1]

            if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{1,2}", number_line) and _is_likely_heading_title(title_line):
                parts = [int(p) for p in number_line.split(".")]
                ch, sub, subsub = parts
                subsubchapter_titles.setdefault((ch, sub, subsub), title_line)
                subsubchapter_start_page.setdefault((ch, sub, subsub), page_num + 1)
                idx += 2
                continue

            if re.fullmatch(r"\d{1,2}\.\d{1,2}", number_line) and _is_likely_heading_title(title_line):
                ch, sub = [int(p) for p in number_line.split(".")]
                subchapter_titles.setdefault((ch, sub), title_line)
                subchapter_counts[(ch, sub)] += 1
                subchapter_start_page.setdefault((ch, sub), page_num + 1)
                idx += 2
                continue

            if re.fullmatch(r"\d{1,2}", number_line) and _is_likely_heading_title(title_line):
                ch = int(number_line)
                chapter_titles.setdefault(ch, title_line)
                chapter_counts[ch] += 1
                idx += 2
                continue

            idx += 1

    doc.close()

    valid_chapters = {
        ch for ch in chapter_titles
        if chapter_counts[ch] >= 2
        or any(ch == c for (c, _) in subchapter_titles.keys())
    }

    valid_subchapters = {
        key for key in subchapter_titles
        if subchapter_counts[key] >= 2
    }

    valid_subsubchapters = set(subsubchapter_titles.keys())

    chapters = []
    for chapter_number in sorted(valid_chapters):
        sub_keys = sorted([
            (s, subchapter_titles[(chapter_number, s)])
            for (c, s) in valid_subchapters if c == chapter_number
        ])

        # Compute end pages for subchapters
        sub_end_pages = {}
        for i, (sub_num, _) in enumerate(sub_keys):
            if i + 1 < len(sub_keys):
                next_start = subchapter_start_page.get((chapter_number, sub_keys[i + 1][0]), total_pages + 1)
                sub_end_pages[sub_num] = next_start - 1
            else:
                sub_end_pages[sub_num] = total_pages

        subchapters = []
        prev_sub_id = None
        for sub_num, sub_title in sub_keys:
            sub_id = f"ch{chapter_number}.{sub_num}"
            sub_start = subchapter_start_page.get((chapter_number, sub_num))
            sub_end = sub_end_pages.get(sub_num, total_pages)

            subsub_keys = sorted([
                (ss, subsubchapter_titles[(chapter_number, sub_num, ss)])
                for (c, s, ss) in valid_subsubchapters if c == chapter_number and s == sub_num
            ])

            # Compute end pages for sub-subchapters
            subsub_end_pages = {}
            for j, (ss_num, _) in enumerate(subsub_keys):
                if j + 1 < len(subsub_keys):
                    next_ss_start = subsubchapter_start_page.get(
                        (chapter_number, sub_num, subsub_keys[j + 1][0]), sub_end + 1
                    )
                    subsub_end_pages[ss_num] = next_ss_start - 1
                else:
                    subsub_end_pages[ss_num] = sub_end

            subsubchapters = []
            prev_ss_id = None
            for ss_num, ss_title in subsub_keys:
                ss_id = f"ch{chapter_number}.{sub_num}.{ss_num}"
                ss_start = subsubchapter_start_page.get((chapter_number, sub_num, ss_num))
                ss_end = subsub_end_pages.get(ss_num, sub_end)
                subsubchapters.append({
                    "id": ss_id,
                    "title": f"{chapter_number}.{sub_num}.{ss_num} {ss_title}",
                    "kcs": [],
                    "prerequisites": [prev_ss_id] if prev_ss_id else [],
                    "start_page": ss_start,
                    "end_page": ss_end,
                })
                prev_ss_id = ss_id

            entry = {
                "id": sub_id,
                "title": f"{chapter_number}.{sub_num} {sub_title}",
                "kcs": [],
                "prerequisites": [prev_sub_id] if prev_sub_id else [],
                "start_page": sub_start,
                "end_page": sub_end,
            }
            if subsubchapters:
                entry["subchapters"] = subsubchapters
            subchapters.append(entry)
            prev_sub_id = sub_id

        chapters.append({
            "id": f"ch{chapter_number}",
            "title": f"{chapter_number}. {chapter_titles[chapter_number]}",
            "subchapters": subchapters,
        })

    return {
        "bookTitle": "Information Systems Management",
        "author": "Krcmar",
        "chapters": chapters,
    }


def _detect_subchapter_on_page(lines: list[str]) -> str | None:
    """Return the subchapter id from running headers on a page."""
    subchapter_id = None
    for i in range(len(lines) - 1):
        if re.fullmatch(r"\d{1,2}\.\d{1,2}", lines[i]) and _is_likely_heading_title(lines[i + 1]):
            ch, sub = lines[i].split(".")
            subchapter_id = f"ch{ch}.{sub}"
    return subchapter_id


def build_index():
    print("Extracting text from all pages of the PDF...")
    doc = fitz.open(PDF_PATH)

    page_docs = []
    total_chars = 0
    current_subchapter_id = None

    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        page_text = page.get_text().strip()
        if not page_text:
            continue

        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        detected = _detect_subchapter_on_page(lines)
        if detected:
            current_subchapter_id = detected

        total_chars += len(page_text)
        page_docs.append(
            Document(
                page_content=page_text,
                metadata={
                    "source": os.path.basename(PDF_PATH),
                    "page_index": page_num,
                    "page_number": page_num + 1,
                    "subchapter_id": current_subchapter_id or "",
                },
            )
        )

    doc.close()
    print(f"Extracted {total_chars} characters across {len(page_docs)} pages. Splitting into chunks...")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", " ", ""]
    )

    chunks = text_splitter.split_documents(page_docs)
    print(f"Created {len(chunks)} chunks. Generating embeddings and building FAISS index...")

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(FAISS_INDEX_PATH)
    print("Index built and saved to disk.")


def get_retriever():
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    if not os.path.exists(FAISS_INDEX_PATH):
        build_index()
    return FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True).as_retriever(search_kwargs={"k": 4})


def get_vectorstore():
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    if not os.path.exists(FAISS_INDEX_PATH):
        build_index()
    return FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)


def get_chunks_for_subchapter(subchapter_id: str) -> list[Document]:
    """All chunks tagged with this subchapter, sorted by page."""
    vectorstore = get_vectorstore()
    all_docs = list(vectorstore.docstore._dict.values())
    matched = [d for d in all_docs if d.metadata.get("subchapter_id") == subchapter_id]
    matched.sort(key=lambda d: d.metadata.get("page_number", 0))
    return matched


def get_chunks_in_page_range(start_page: int, end_page: int) -> list[Document]:
    """All chunks whose page_number falls within [start_page, end_page] (1-indexed)."""
    vectorstore = get_vectorstore()
    all_docs = list(vectorstore.docstore._dict.values())
    matched = [d for d in all_docs if start_page <= d.metadata.get("page_number", 0) <= end_page]
    matched.sort(key=lambda d: d.metadata.get("page_number", 0))
    return matched


def get_text_for_page_range(start_page: int, end_page: int) -> str:
    """Extract raw text directly from PDF for pages [start_page, end_page] (1-indexed).
    More reliable than vectorstore for section-scoped queries."""
    doc = fitz.open(PDF_PATH)
    try:
        texts = []
        for page_num in range(start_page - 1, min(end_page, doc.page_count)):
            texts.append(doc.load_page(page_num).get_text())
        return "\n\n".join(texts)
    finally:
        doc.close()


def render_page_as_png(page_number: int, zoom: float = 1.5) -> bytes:
    """Render a 1-indexed PDF page as PNG bytes."""
    doc = fitz.open(PDF_PATH)
    try:
        page = doc.load_page(page_number - 1)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    finally:
        doc.close()


def get_figures_in_page_range(start_page: int, end_page: int) -> list[dict]:
    """
    Return metadata for all embedded images in [start_page, end_page] (1-indexed).
    Each entry: { page, xref, caption, width, height }
    Caption is extracted from 'Abb.' lines on the same page.
    """
    doc = fitz.open(PDF_PATH)
    figures = []
    seen_xrefs = set()
    try:
        for page_num in range(start_page - 1, min(end_page, doc.page_count)):
            page = doc.load_page(page_num)
            imgs = page.get_images(full=True)
            if not imgs:
                continue
            lines = [l.strip() for l in page.get_text().splitlines() if l.strip()]
            captions = [l for l in lines if l.startswith("Abb.")]
            for img_idx, img in enumerate(imgs):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                info = doc.extract_image(xref)
                caption = captions[img_idx] if img_idx < len(captions) else ""
                figures.append({
                    "page": page_num + 1,
                    "xref": xref,
                    "caption": caption,
                    "width": info["width"],
                    "height": info["height"],
                })
    finally:
        doc.close()
    return figures


def get_figure_image(xref: int) -> bytes:
    """Return raw image bytes for a figure by its xref."""
    doc = fitz.open(PDF_PATH)
    try:
        info = doc.extract_image(xref)
        return info["image"]
    finally:
        doc.close()


def render_figure_region(
    page_number: int,
    ref_key: str | None = None,
    caption: str | None = None,
    zoom: float = 2.0,
) -> bytes:
    """Render a cropped figure region from a page using caption position heuristics.

    The crop prefers embedded image or vector drawing regions located directly above
    the matching figure caption. Falls back to a broad area above the caption.
    """
    doc = fitz.open(PDF_PATH)
    try:
        page = doc.load_page(page_number - 1)
        page_rect = page.rect

        caption_rect = None

        # Prefer searching by stable figure marker, e.g. "Abb. 3.1".
        if ref_key:
            marker = f"Abb. {ref_key}"
            hits = page.search_for(marker)
            if hits:
                caption_rect = hits[0]

        # Fallback: search by full caption text.
        if caption_rect is None and caption:
            hits = page.search_for(caption)
            if hits:
                caption_rect = hits[0]

        # Last fallback: locate any block containing the marker.
        if caption_rect is None and ref_key:
            marker = f"Abb. {ref_key}"
            for b in page.get_text("blocks"):
                rect = fitz.Rect(b[:4])
                txt = (b[4] or "").strip()
                if marker in txt:
                    caption_rect = rect
                    break

        clip_rect = None
        if caption_rect:
            cap_top = caption_rect.y0
            caption_rects = page.search_for("Abb.")
            prev_caption_bottom = page_rect.y0 + 24
            for r in caption_rects:
                if r.y1 < caption_rect.y0 and r.y1 > prev_caption_bottom:
                    prev_caption_bottom = r.y1

            # Candidate window: between previous caption and this caption.
            y_low = prev_caption_bottom + 4
            y_high = cap_top + 10

            image_rects = []
            for img in page.get_images(full=True):
                xref = img[0]
                for rect in page.get_image_rects(xref):
                    if rect.y0 >= y_low and rect.y1 <= y_high:
                        image_rects.append(rect)

            if image_rects:
                # For embedded images, the nearest full image above the caption is usually correct.
                image_rects.sort(key=lambda r: (cap_top - r.y1, -(r.width * r.height)))
                base = image_rects[0]
                clip_rect = fitz.Rect(base.x0 - 8, base.y0 - 8, base.x1 + 8, base.y1 + 8)
            else:
                draw_rects = []
                for drawing in page.get_drawings():
                    rect = drawing.get("rect")
                    if not rect:
                        continue
                    if rect.y0 >= y_low and rect.y1 <= y_high and rect.width * rect.height > 40:
                        draw_rects.append(rect)

                if draw_rects:
                    # Vector figures are often split into many tiny paths; union all paths
                    # in the caption window to reconstruct the full diagram footprint.
                    x0 = min(r.x0 for r in draw_rects)
                    y0 = min(r.y0 for r in draw_rects)
                    x1 = max(r.x1 for r in draw_rects)
                    y1 = max(r.y1 for r in draw_rects)
                    union = fitz.Rect(x0, y0, x1, y1)

                    # Pull in nearby text blocks (labels inside diagrams).
                    expanded = fitz.Rect(union.x0 - 14, union.y0 - 14, union.x1 + 14, union.y1 + 14)
                    text_blocks = page.get_text("blocks")
                    for b in text_blocks:
                        trect = fitz.Rect(b[:4])
                        ttxt = (b[4] or "").strip()
                        if not ttxt:
                            continue
                        if trect.y0 >= y_low and trect.y1 <= y_high and expanded.intersects(trect):
                            union |= trect

                    clip_rect = fitz.Rect(union.x0 - 10, union.y0 - 10, union.x1 + 10, union.y1 + 10)
                else:
                    # Final fallback: broad area above caption.
                    top = max(page_rect.y0 + 20, cap_top - page_rect.height * 0.6)
                    bottom = min(page_rect.y1, caption_rect.y1 + 6)
                    clip_rect = fitz.Rect(page_rect.x0 + 8, top, page_rect.x1 - 8, bottom)
        else:
            clip_rect = page_rect

        clip_rect = clip_rect & page_rect
        if clip_rect.is_empty or clip_rect.width < 10 or clip_rect.height < 10:
            clip_rect = page_rect

        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip_rect)
        return pix.tobytes("png")
    finally:
        doc.close()


def build_figure_index() -> dict:
    """
    Scan every page for 'Abb. X.Y' captions and return a mapping:
      { "3.1": {"page": 5, "caption": "Abb. 3.1 ..."}, ... }
    Covers both embedded-image figures and vector diagrams.
    """
    doc = fitz.open(PDF_PATH)
    index = {}
    try:
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            text = page.get_text()
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            captions = []

            for line in lines:
                line = line.strip()
                m = re.match(r"^(Abb\.\s*(\d+\.\d+))\b(.*)", line)
                if m:
                    captions.append(line)
                    ref_key = m.group(2)          # e.g. "3.1"
                    full_caption = (m.group(1) + m.group(3)).strip()
                    if ref_key not in index:      # keep first occurrence
                        index[ref_key] = {
                            "page": page_num + 1,
                            "caption": full_caption,
                        }

            caption_entries = []
            for caption in captions:
                m = re.match(r"^Abb\.\s*(\d+\.\d+)\b", caption)
                if not m:
                    continue
                ref_key = m.group(1)
                marker_hits = page.search_for(f"Abb. {ref_key}")
                if marker_hits:
                    caption_entries.append((ref_key, marker_hits[0]))

            caption_entries.sort(key=lambda x: x[1].y0)

            image_rects = []
            for img in page.get_images(full=True):
                xref = img[0]
                for rect in page.get_image_rects(xref):
                    image_rects.append((xref, rect))

            for i, (ref_key, cap_rect) in enumerate(caption_entries):
                if ref_key not in index:
                    continue

                prev_caption_bottom = page.rect.y0 + 24
                if i > 0:
                    prev_caption_bottom = max(prev_caption_bottom, caption_entries[i - 1][1].y1)

                candidates = []
                for xref, rect in image_rects:
                    if rect.y0 >= prev_caption_bottom and rect.y1 <= cap_rect.y0 + 10:
                        gap = cap_rect.y0 - rect.y1
                        area = rect.width * rect.height
                        candidates.append((gap, -area, xref))

                if candidates:
                    candidates.sort()
                    index[ref_key]["xref"] = candidates[0][2]
    finally:
        doc.close()
    return index


if __name__ == "__main__":
    build_index()
