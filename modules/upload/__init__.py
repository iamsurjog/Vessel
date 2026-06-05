import operator
import subprocess
import re
import json
import tempfile
from pathlib import Path
from collections import Counter
from html.parser import HTMLParser
from typing import Annotated, List, TypedDict

from langgraph.graph import START, END, StateGraph
import sqlite3
import sqlite_vec
import httpx


# ==========================================
# 1. THE ARCHITECTURE STATE
# ==========================================
class IngestionState(TypedDict):
    file_path: str
    file_type: str            # 'ppt', 'doc', 'pdf', 'html', 'txt', 'image', 'video'
    extracted_text: str
    description: str
    # 'operator.add' lets your bottom 3 parallel nodes safely save results together
    db_logs: Annotated[List[str], operator.add]


# ==========================================
# 2. HELPERS
# ==========================================

def _locate_vessel(file_path: str):
    """
    Derive the vessel root, DB path, and content dir from any file
    that lives under a Vessel directory tree.
    The DB layout is defined in modules/__init__.py -> initVessel().
    """
    p = Path(file_path).resolve()
    parts = p.parts
    for i, part in enumerate(parts):
        if part in ("Materials", "Droplets", "AI"):
            root = Path(*parts[:i])
            db_path = root / ".vessel" / "vessel_rag.db"
            content_dir = root / "AI" / "content"
            content_dir.mkdir(parents=True, exist_ok=True)
            return root, db_path, content_dir
    raise ValueError(
        f"Cannot determine Vessel root from '{file_path}'. "
        f"File must be inside a Vessel's Materials/, Droplets/, or AI/ directory."
    )


def _open_rag_db(db_path: Path) -> sqlite3.Connection:
    """Open a connection to the vessel RAG DB with sqlite-vec loaded."""
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _get_or_create_document(cursor, title: str, text_preview: str) -> int:
    """
    INSERT-or-catch pattern — safe against concurrent INSERT races
    because `documents.title` now has a UNIQUE constraint.
    """
    try:
        cursor.execute(
            "INSERT INTO documents (title, text_chunk) VALUES (?, ?)",
            (title, text_preview),
        )
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        cursor.execute(
            "SELECT id FROM documents WHERE title = ?", (title,)
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0]
        raise  # should not happen, but safety net


# ==========================================
# 2b. TAG EXTRACTION (aggressive — false-positive tolerant)
# ==========================================

# Stop-words too common to be useful as tags
_STOP_WORDS: set[str] = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "have", "been", "some",
    "them", "than", "that", "this", "very", "just", "also", "its",
    "over", "such", "with", "will", "each", "make", "like", "from",
    "how", "what", "when", "where", "which", "who", "whom", "why",
    "more", "most", "many", "much", "any", "every", "else",
    "less", "few", "both", "into", "about", "could", "would", "should",
    "might", "must", "shall", "than", "then", "there", "their", "they",
    "them", "these", "those", "been", "being", "done", "does", "doing",
    "having", "going", "said", "get", "got", "see", "seen", "way",
    "well", "back", "still", "even", "too", "here", "there", "down",
    "first", "last", "next", "other", "another", "same", "old", "new",
    "up", "off", "never", "ever", "own", "part", "take", "made", "make",
    "use", "used", "using", "uses", "based", "via", "thus", "hence",
    "also", "well", "however", "therefore", "following", "within",
    "without", "across", "along", "among", "above", "below",
    "before", "after", "during", "while", "since", "until",
    "upon", "onto", "unto", "about", "around", "behind", "beneath",
    "beside", "between", "beyond", "through", "throughout", "toward",
    "towards", "under", "underneath", "unless", "unlike", "until",
}


def _extract_tags(
    text: str,
    file_name: str,
    file_type: str,
    max_tags: int = 30,
) -> list[str]:
    """
    Extract candidate tags from document text using multiple strategies.

    Returns at most *max_tags* tags sorted by estimated specificity.
    Designed to over-generate — false positives are preferred over
    missed tags for recall-heavy RAG retrieval.
    """
    candidates: dict[str, int] = Counter()

    stem = Path(file_name).stem
    ext = Path(file_name).suffix.lower().lstrip(".")

    # ── Strategy 1: File identity ──────────────────────────────────
    candidates[f"type:{file_type}"] += 10
    if ext:
        candidates[ext] += 8
        candidates[f"ext:{ext}"] += 6

    # ── Strategy 2: File-name parts (split on _ - . space) ─────────
    for sep in ("_", "-", ".", " "):
        for part in stem.split(sep):
            part = part.strip().lower()
            if len(part) >= 3 and part not in _STOP_WORDS:
                candidates[part] += 5

    if not text:
        return [t for t, _ in candidates.most_common(max_tags)]

    # ── Strategy 3: All significant lowercase words ────────────────
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    for w in words:
        if w not in _STOP_WORDS and not w.isdigit():
            candidates[w] += 1

    # ── Strategy 4: Title-Cased words (proper nouns / concepts) ────
    title_words = re.findall(r"\b[A-Z][a-z]{2,}\b", text)
    for w in title_words:
        if w.lower() not in _STOP_WORDS:
            candidates[w] += 3

    # ── Strategy 5: Title-Cased multi-word phrases (2–5 words) ─────
    phrases = re.findall(r"(?:[A-Z][a-z]{2,}\s+){1,4}[A-Z][a-z]{2,}", text)
    for ph in phrases:
        ph = ph.strip()
        if len(ph) > 6 and ph.lower() not in _STOP_WORDS:
            candidates[ph] += 4

    # ── Strategy 6: ALL-CAPS acronyms / abbreviations ──────────────
    acronyms = re.findall(r"\b[A-Z]{2,6}\b", text)
    for a in acronyms:
        if len(a) >= 2:
            candidates[a] += 4

    # ── Strategy 7: CamelCase identifiers (API names, classes) ─────
    camel = re.findall(r"\b[A-Z][a-z]+[A-Z][a-zA-Z]+\b", text)
    for c in camel:
        candidates[c] += 3

    # ── Strategy 8: Numbers — years, percentages, quantities ───────
    numbers = re.findall(r"\b\d{3,}\b", text)
    for n in numbers:
        candidates[f"num:{n}"] += 2

    # ── Strategy 9: Hyphenated compounds ────────────────────────────
    hyphens = re.findall(r"\b[a-zA-Z]{3,}(?:-[a-zA-Z]{3,})+\b", text)
    for h in hyphens:
        candidates[h] += 3

    # ── Strategy 10: Repeated / frequent single words (TF signal) ──
    # Already captured via Counter above; we just sort by frequency now.

    # Boost short tags that look like jargon (3–4 chars, not in stop list)
    boosted: list[tuple[int, str]] = []
    for tag, score in candidates.items():
        display_score = score
        if 3 <= len(tag) <= 4 and tag.lower() not in _STOP_WORDS:
            display_score += 2  # short tokens are often domain-specific
        # Penalize very long multi-word tags slightly
        if len(tag) > 40:
            display_score -= 2
        boosted.append((display_score, tag))

    # Sort: highest score first; ties → longer tag first (more specific)
    boosted.sort(key=lambda x: (-x[0], -len(x[1]), x[1]))

    return [tag for _, tag in boosted[:max_tags]]


# ==========================================
# 3. GRAPH NODES
# ==========================================

# -- Phase 1: Conversion & Extraction Nodes --------------------------------

async def convert_to_pdf_node(state: IngestionState):
    """Convert .ppt / .pptx / .doc / .docx -> PDF via LibreOffice CLI."""
    source = Path(state["file_path"])
    if not source.exists():
        return {"db_logs": [f"\u274c [convert_to_pdf] File not found: {source}"]}

    pdf_path = source.with_suffix(".pdf")
    if pdf_path.exists():
        return {
            "file_path": str(pdf_path),
            "file_type": "pdf",
            "db_logs": [f"\u2713 [convert_to_pdf] {pdf_path.name} already exists, reusing."]
        }

    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(source.parent), str(source)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {"db_logs": [f"\u274c [convert_to_pdf] LibreOffice failed: {result.stderr}"]}
    except FileNotFoundError:
        return {"db_logs": ["\u274c [convert_to_pdf] LibreOffice not found — install it or use a compatible format."]}
    except subprocess.TimeoutExpired:
        return {"db_logs": ["\u274c [convert_to_pdf] LibreOffice timed out after 120 s."]}

    return {
        "file_path": str(pdf_path),
        "file_type": "pdf",
        "db_logs": [f"\u2713 [convert_to_pdf] {source.name} -> {pdf_path.name}"],
    }


async def extract_text_node(state: IngestionState):
    """Extract clean text from PDF / TXT / HTML files."""
    source = Path(state["file_path"])
    if not source.exists():
        return {"db_logs": [f"\u274c [extract_text] File not found: {source}"]}

    f_type = state["file_type"].lower()
    text = ""

    # --- PDF: use pdftotext (poppler-utils); fallback to PyMuPDF if available ---
    if f_type == "pdf":
        try:
            r = subprocess.run(
                ["pdftotext", "-layout", str(source), "-"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                text = r.stdout
        except FileNotFoundError:
            pass

        if not text.strip():
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(source))
                text = "\n\n".join(page.get_text() for page in doc)
                doc.close()
            except ImportError:
                text = (
                    f"[PDF text extraction requires pdftotext (poppler-utils) "
                    f"or PyMuPDF — both unavailable; unable to parse '{source.name}']"
                )

    # --- TXT: direct read ---
    elif f_type == "txt":
        text = source.read_text(encoding="utf-8", errors="replace")

    # --- HTML: strip tags via stdlib HTMLParser ---
    elif f_type == "html":
        raw = source.read_text(encoding="utf-8", errors="replace")

        class _StripHTML(HTMLParser):
            def __init__(self):
                super().__init__()
                self._out = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style"):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ("script", "style"):
                    self._skip = False
            def handle_data(self, data):
                if not self._skip:
                    self._out.append(data)
            def result(self):
                return " ".join(self._out)

        parser = _StripHTML()
        parser.feed(raw)
        text = parser.result()

    else:
        text = f"[extract_text] Unsupported file type '{f_type}' for direct extraction."

    return {
        "extracted_text": text.strip(),
        "db_logs": [f"\u2713 [extract_text] Extracted {len(text.strip())} chars from '{source.name}'"],
    }


async def generate_description_node(state: IngestionState):
    """
    Generate a description and optional text for image / video files.
    - Images: Tesseract OCR
    - Videos: Single-frame grab + Tesseract OCR
    """
    source = Path(state["file_path"])
    if not source.exists():
        return {"db_logs": [f"\u274c [describe] File not found: {source}"]}

    f_type = state["file_type"].lower()
    extracted_text = ""
    description = ""

    # --- Image -> OCR via tesseract ---
    if f_type == "image":
        try:
            r = subprocess.run(
                ["tesseract", str(source), "stdout", "-l", "eng"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                extracted_text = r.stdout.strip()
        except FileNotFoundError:
            pass

        description = f"Image: {source.name}"
        if extracted_text:
            description += f" | OCR text ({len(extracted_text)} chars)"

    # --- Video -> extract one frame and OCR it ---
    elif f_type == "video":
        frame_text = ""
        try:
            with tempfile.TemporaryDirectory() as tmp:
                frame = Path(tmp) / "frame.jpg"
                subprocess.run(
                    ["ffmpeg", "-i", str(source), "-vframes", "1",
                     "-q:v", "2", str(frame)],
                    capture_output=True, timeout=120,
                )
                if frame.exists():
                    r = subprocess.run(
                        ["tesseract", str(frame), "stdout", "-l", "eng"],
                        capture_output=True, text=True, timeout=30,
                    )
                    if r.returncode == 0:
                        frame_text = r.stdout.strip()
        except FileNotFoundError:
            pass

        description = f"Video: {source.name}"
        if frame_text:
            extracted_text = frame_text
            description += f" | Frame OCR ({len(frame_text)} chars)"
        else:
            description += " | No OCR text extracted from sample frame"

    if not description:
        description = f"{f_type.capitalize()}: {source.name} ({source.stat().st_size} bytes)"

    return {
        "description": description,
        "extracted_text": extracted_text or description,
        "db_logs": [f"\u2713 [describe] Generated description for '{source.name}'"],
    }


# -- Phase 2: Downstream Storage Nodes (run in parallel) -------------------

async def create_and_store_vec_embeddings(state: IngestionState):
    """
    Generate a vector embedding for the extracted text and persist it in
    the sqlite-vec virtual table (v_document_embeddings).

    Embedding source (tried in order):
      1. ollama API at localhost:11434 (model: nomic-embed-text)
      2. sentence-transformers (all-MiniLM-L6-v2) if installed
    """
    text = (state.get("extracted_text") or state.get("description") or "").strip()
    if not text:
        return {"db_logs": ["\u26a0\ufe0f [embed] No text to embed — skipping."]}

    source_name = Path(state["file_path"]).name
    _, db_path, _ = _locate_vessel(state["file_path"])

    # ----- Generate embedding vector -----
    embedding = None

    # Strategy 1: ollama API
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "http://localhost:11434/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text[:2048]},
            )
            if resp.status_code == 200:
                embedding = resp.json().get("embedding")
    except Exception:
        pass

    # Strategy 2: sentence-transformers
    if embedding is None:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embedding = model.encode(text[:2048]).tolist()
        except ImportError:
            pass

    if embedding is None:
        return {
            "db_logs": [
                "\u274c [embed] No embedding model available.\n"
                "  Install ollama + nomic-embed-text, or run:\n"
                "    pip install sentence-transformers"
            ]
        }

    # ----- Store in sqlite-vec -----
    try:
        conn = _open_rag_db(db_path)
        cur = conn.cursor()

        doc_id = _get_or_create_document(cur, source_name, text[:2000])

        cur.execute(
            "INSERT INTO v_document_embeddings (rowid, embedding) VALUES (?, ?)",
            (doc_id, embedding),
        )
        conn.commit()
        conn.close()

        return {
            "db_logs": [
                f"\u2713 [embed] Stored {len(embedding)}-dim vector "
                f"for '{source_name}' (doc_id={doc_id})"
            ]
        }
    except Exception as e:
        return {"db_logs": [f"\u274c [embed] DB error: {e}"]}


async def store_txt_as_file(state: IngestionState):
    """Persist the extracted text as a .txt file under AI/content/."""
    text = (state.get("extracted_text") or state.get("description") or "").strip()
    if not text:
        return {"db_logs": ["\u26a0\ufe0f [store_txt] No text to persist — skipping."]}

    _, _, content_dir = _locate_vessel(state["file_path"])
    stem = Path(state["file_path"]).stem

    txt_path = content_dir / f"{stem}.txt"
    if txt_path.exists():
        counter = 1
        while txt_path.exists():
            txt_path = content_dir / f"{stem}_{counter}.txt"
            counter += 1

    txt_path.write_text(text, encoding="utf-8")

    return {
        "db_logs": [
            f"\u2713 [store_txt] Saved {len(text)} chars -> "
            f"'{txt_path.relative_to(content_dir.parent)}'"
        ]
    }


async def create_and_store_tags(state: IngestionState):
    """
    Aggressively extract tags from the document text using 10 strategies,
    then persist them in the tags + document_tags junction tables.

    False-positive tolerant: prefers over-tagging over under-tagging.
    """
    text = (state.get("extracted_text") or state.get("description") or "").strip()
    f_type = state["file_type"].lower()
    source_name = Path(state["file_path"]).name

    tags = _extract_tags(text, source_name, f_type, max_tags=30)

    if not tags:
        tags = ["untagged"]

    # ----- Persist in DB -----
    _, db_path, _ = _locate_vessel(state["file_path"])

    try:
        conn = _open_rag_db(db_path)
        cur = conn.cursor()

        doc_id = _get_or_create_document(cur, source_name, text[:2000])

        for tag_name in tags:
            cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
            cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = cur.fetchone()[0]
            cur.execute(
                "INSERT OR IGNORE INTO document_tags (doc_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_id),
            )

        conn.commit()
        conn.close()

        return {
            "db_logs": [
                f"\u2713 [tags] Tagged '{source_name}' (doc_id={doc_id}) "
                f"with {len(tags)} tags: {', '.join(sorted(tags))}"
            ]
        }
    except Exception as e:
        return {"db_logs": [f"\u274c [tags] DB error: {e}"]}


# ==========================================
# 4. ROUTER CONDITIONAL EDGES
# ==========================================
def filetype_router(state: IngestionState) -> str:
    f_type = state["file_type"].lower()

    if f_type in ("ppt", "doc"):
        return "route_to_converter"
    elif f_type in ("pdf", "txt", "html"):
        return "route_to_extractor"
    elif f_type in ("image", "video"):
        return "route_to_descriptor"

    return "route_to_extractor"


# ==========================================
# 5. BUILD THE GRAPH
# ==========================================
workflow = StateGraph(IngestionState)

workflow.add_node("convert_to_pdf_node", convert_to_pdf_node)
workflow.add_node("extract_text_node", extract_text_node)
workflow.add_node("generate_description_node", generate_description_node)

workflow.add_node("create_and_store_vec_embeddings", create_and_store_vec_embeddings)
workflow.add_node("store_txt_as_file", store_txt_as_file)
workflow.add_node("create_and_store_tags", create_and_store_tags)

workflow.add_conditional_edges(
    START,
    filetype_router,
    {
        "route_to_converter": "convert_to_pdf_node",
        "route_to_extractor": "extract_text_node",
        "route_to_descriptor": "generate_description_node"
    }
)

workflow.add_edge("convert_to_pdf_node", "extract_text_node")

workflow.add_edge("extract_text_node", "create_and_store_vec_embeddings")
workflow.add_edge("extract_text_node", "store_txt_as_file")
workflow.add_edge("extract_text_node", "create_and_store_tags")

workflow.add_edge("generate_description_node", "create_and_store_vec_embeddings")
workflow.add_edge("generate_description_node", "store_txt_as_file")
workflow.add_edge("generate_description_node", "create_and_store_tags")

workflow.add_edge("create_and_store_vec_embeddings", END)
workflow.add_edge("store_txt_as_file", END)
workflow.add_edge("create_and_store_tags", END)

app = workflow.compile()
