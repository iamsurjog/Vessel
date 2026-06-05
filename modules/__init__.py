import asyncio
from pathlib import Path
from typing import Optional
import sqlite3
import sqlite_vec


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open a connection with sqlite-vec loaded and foreign keys on."""
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# UPLOAD PIPELINE  — called after a file is copied into Materials/
# ---------------------------------------------------------------------------

def updateEmbeds(file_path: str) -> bool:
    """
    Run the full upload ingestion pipeline on a newly added Material file.

    1. Infer file type from extension
    2. Extract / convert text (PDF → pdftotext, TXT → direct, HTML → strip,
       PPT/DOC → LibreOffice → PDF → extract, Image → OCR, Video → frame OCR)
    3. Store extracted text as a .txt in AI/content/
    4. Generate extensive tags
    5. Store vector embedding (if an embedding model is available)
    6. The FTS5 index is automatically kept in sync via DB triggers

    This is the single entry-point intended for use from main.py.
    """
    try:
        from modules.upload import app as upload_graph

        source = Path(file_path)

        # Map extension → file type
        ext = source.suffix.lower()
        type_map = {
            ".ppt": "ppt", ".pptx": "ppt",
            ".doc": "doc", ".docx": "doc",
            ".pdf": "pdf",
            ".htm": "html", ".html": "html",
            ".txt": "txt",
            ".png": "image", ".jpg": "image", ".jpeg": "image",
            ".gif": "image", ".bmp": "image", ".webp": "image", ".svg": "image",
            ".mp4": "video", ".avi": "video", ".mov": "video",
            ".mkv": "video", ".webm": "video",
        }
        f_type = type_map.get(ext, "txt")

        result = asyncio.run(
            upload_graph.ainvoke({
                "file_path": str(source.resolve()),
                "file_type": f_type,
                "extracted_text": "",
                "description": "",
                "db_logs": [],
            })
        )

        for log in result.get("db_logs", []):
            print(f"  {log}")

        return True

    except Exception as e:
        print(f"❌ updateEmbeds failed for '{file_path}': {e}")
        return False


# ---------------------------------------------------------------------------
# BM25 SEARCH  — SQLite FTS5 full-text search with BM25 ranking
# ---------------------------------------------------------------------------

def bm25_search(db_path: Path, query: str, top_k: int = 10) -> list[dict]:
    """
    Search document chunks with BM25 ranking via SQLite FTS5.

    Returns list of:
        {"id": int, "title": str, "text_chunk": str, "rank": float}
    sorted by relevance (best first).
    """
    if not query.strip():
        return []

    try:
        conn = _open_db(db_path)
        cur = conn.cursor()

        # FTS5 query syntax: clean the user query into terms joined by OR
        # so even partial matches surface results (recall > precision).
        terms = [
            t.strip().rstrip(",.!?;:")
            for t in query.split()
            if len(t.strip()) > 1
        ]
        if not terms:
            conn.close()
            return []

        # Hyphens trigger FTS5 column-reference parsing — replace with spaces.
        # (The indexed content already tokenizes hyphens as separators, so
        #  searching for "full text" correctly matches "full-text" in content.)
        sanitised = [t.replace("-", " ") for t in terms]
        fts_query = " OR ".join(sanitised)

        rows = cur.execute(
            """
            SELECT d.id, d.title, d.text_chunk, bm25(documents_fts, 0.0, 1.0) AS rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, top_k),
        ).fetchall()

        conn.close()

        return [
            {"id": r[0], "title": r[1], "text_chunk": r[2], "rank": r[3]}
            for r in rows
        ]

    except Exception as e:
        print(f"❌ BM25 search error: {e}")
        return []


# ---------------------------------------------------------------------------
# TAG-BASED SEARCH  (inverted-index lookup via junction table)
# ---------------------------------------------------------------------------

def tag_search(db_path: Path, tag_names: list[str]) -> list[dict]:
    """Find documents that match *any* of the given tags."""
    if not tag_names:
        return []

    try:
        conn = _open_db(db_path)
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in tag_names)

        rows = cur.execute(
            f"""
            SELECT DISTINCT d.id, d.title, d.text_chunk
            FROM documents d
            JOIN document_tags dt ON dt.doc_id = d.id
            JOIN tags t ON t.id = dt.tag_id
            WHERE t.name IN ({placeholders})
            ORDER BY d.id
            """,
            tag_names,
        ).fetchall()

        conn.close()
        return [
            {"id": r[0], "title": r[1], "text_chunk": r[2]}
            for r in rows
        ]

    except Exception as e:
        print(f"❌ Tag search error: {e}")
        return []


def get_all_documents(db_path: Path) -> list[dict]:
    """Return every document row from the database — no search, no ranking."""
    try:
        conn = _open_db(db_path)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, title, text_chunk FROM documents ORDER BY id"
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "title": r[1], "text_chunk": r[2]}
            for r in rows
        ]
    except Exception as e:
        print(f"❌ get_all_documents error: {e}")
        return []


# ---------------------------------------------------------------------------
# QUERY ENTRY POINT  (bridge from the Qt UI → LangGraph query engine)
# ---------------------------------------------------------------------------

def answerTo(
    vessel_path: str,
    query: str,
    web_search_enabled: bool = False,
    chat_history: list[dict] | None = None,
    provider_config: dict | None = None,
) -> str:
    """
    Answer a user query by running the full LangGraph query pipeline:
    classify → (vector + BM25 + optional web search) → generate answer.

    Parameters
    ----------
    vessel_path : str
        Path to the vessel root directory.
    query : str
        The user's question or request.
    web_search_enabled : bool
        Whether to also query DuckDuckGo for web results.
    chat_history : list[dict] | None
        Previous messages in the conversation, each with
        ``{"sender": "user"|"model", "text": "..."}`` for conversational context.
    provider_config : dict | None
        Provider configuration dict with keys:
        provider (str), ollama_model (str),
        openai_api_key (str), anthropic_api_key (str), google_api_key (str),
        openai_model (str), anthropic_model (str), google_model (str).

    Returns
    -------
    str
        The final answer formatted for display.
    """
    from modules.query import app as query_app

    # Normalise chat_history to Ollama format
    history: list[dict] = []
    if chat_history:
        for msg in chat_history:
            sender = msg.get("sender", "user")
            role = "assistant" if sender == "model" else "user"
            text = msg.get("text", "")
            if text.strip():
                history.append({"role": role, "content": text.strip()})

    if provider_config is None:
        provider_config = {}

    try:
        result = query_app.invoke({
            "query": query,
            "vessel_path": vessel_path,
            "web_search_enabled": web_search_enabled,
            "action_type": "",
            "require_calculation": False,
            "is_relevant": True,
            "retrieved_contexts": [],
            "generated_script_output": "",
            "final_answer": "",
            "topic_keyword": "",
            "answer_quality_score": 0,
            "refinement_attempts": 0,
            "refinement_feedback": "",
            "max_refinements": 3,
            "chat_history": history,
            "provider_config": provider_config,
        })

        answer = result.get("final_answer", "")
        return answer if answer else "*No answer could be generated.*"

    except Exception as e:
        return f"*Failed to run query pipeline:* `{e}`"


# ---------------------------------------------------------------------------
# VESSEL INITIALIZATION
# ---------------------------------------------------------------------------

def initVessel(path: Path) -> bool:
    """
    Create the full database schema for a new vessel:

      documents           — id / title / text_chunk
      tags                — id / name (unique)
      document_tags       — (doc_id, tag_id) junction
      v_document_embeddings — sqlite-vec vector table (768-d)
      documents_fts       — FTS5 full-text index (synced via triggers)

    Also enforces a UNIQUE constraint on documents.title so that the
    upload pipeline is safe against concurrent INSERT races.
    """
    sys_dir = path / ".vessel"
    content_dir = path / "AI" / "content"
    sys_dir.mkdir(parents=True, exist_ok=True)
    content_dir.mkdir(parents=True, exist_ok=True)

    db_file = sys_dir / "vessel_rag.db"

    try:
        conn = sqlite3.connect(str(db_file))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # ── Document store ─────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                text_chunk TEXT NOT NULL
            );
        """)
        # Unique title prevents duplicate document rows during parallel ingestion
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_title ON documents(title);")

        # ── Tags (inverted-index search) ───────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_tags (
                doc_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (doc_id, tag_id),
                FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_search ON document_tags(tag_id, doc_id);")

        # ── Vector embeddings ─────────────────────────────────────────
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS v_document_embeddings USING vec0(
                embedding float[768]
            );
        """)

        # ── FTS5 full-text index for BM25 search ──────────────────────
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title, text_chunk,
                content='documents',
                content_rowid='id'
            );
        """)

        # Sync triggers — keep FTS in sync with documents table
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_fts_ai
            AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, text_chunk)
                VALUES (new.id, new.title, new.text_chunk);
            END;
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_fts_ad
            AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, text_chunk)
                VALUES ('delete', old.id, old.title, old.text_chunk);
            END;
        """)
        # UPDATE = DELETE old + INSERT new (FTS5 has no UPDATE)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_fts_au
            AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, text_chunk)
                VALUES ('delete', old.id, old.title, old.text_chunk);
                INSERT INTO documents_fts(rowid, title, text_chunk)
                VALUES (new.id, new.title, new.text_chunk);
            END;
        """)

        # Backfill FTS for any documents inserted before FTS was created
        cursor.execute("""
            INSERT INTO documents_fts(rowid, title, text_chunk)
            SELECT d.id, d.title, d.text_chunk
            FROM documents d
            WHERE d.id NOT IN (SELECT rowid FROM documents_fts);
        """)

        conn.commit()
        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"❌ Database Initialization failed: {e}")
        return False
