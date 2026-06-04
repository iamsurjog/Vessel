import json
import operator
import sys as _sys
from pathlib import Path
from typing import Annotated, List, TypedDict
from langgraph.graph import START, END, StateGraph
import sqlite3
import sqlite_vec

from modules import bm25_search, get_all_documents, tag_search


# ==========================================
# 1. THE QUERY ENGINE STATE
# ==========================================
class QueryEngineState(TypedDict):
    query: str
    action_type: str  # 'answer_q' or 'summarize_generate'
    web_search_enabled: bool
    require_calculation: bool
    is_relevant: bool
    vessel_path: str  # so BM25 / vector / tag nodes know where the DB is

    # 'operator.add' aggregates multi-channel search results seamlessly
    retrieved_contexts: Annotated[List[str], operator.add]
    generated_script_output: str
    final_answer: str

    # Topic keyword extracted from summarize queries; "" = fetch all documents
    topic_keyword: str

    # Conversational context from prior turns
    chat_history: list[dict]      # [{role: "user"|"assistant", content: "..."}, …]

    # Multi-pass answer refinement
    answer_quality_score: int     # 0-10 rating from quality check
    refinement_attempts: int      # how many times we've refined so far
    refinement_feedback: str      # specific feedback from quality check
    max_refinements: int          # max refinement iterations (default 3)


# ==========================================
# 2. OLLAMA HELPERS
# ==========================================
_OLLAMA_BASE = "http://localhost:11434"
_OLLAMA_MODEL = "tinyllama:1.1b"


_OLLAMA_SYSTEM = "Answer directly. No prefacing. No commentary."

def _ollama_chat(
    messages: list[dict], model: str = _OLLAMA_MODEL, timeout: int = 120
) -> str | None:
    """Call Ollama chat API. Returns response content or None on failure.

    Uses streaming to work around httpx hanging on non-streamed POST.
    Handles thinking models (DeepSeek-R1 distilled) where final
    content may arrive in the ``message.content`` field or the
    ``thinking`` field — whichever is non-empty wins.
    """
    try:
        import httpx, json

        # Prepend system message if caller didn't supply one
        if not any(m.get("role") == "system" for m in messages):
            messages = [{"role": "system", "content": _OLLAMA_SYSTEM}] + messages

        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            with client.stream(
                "POST",
                f"{_OLLAMA_BASE}/api/chat",
                json={"model": model, "messages": messages, "stream": True},
            ) as resp:
                if resp.status_code != 200:
                    return None
                content_parts: list[str] = []
                thinking_parts: list[str] = []
                buf = b""
                for chunk in resp.iter_bytes():
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            d = json.loads(line)
                            msg = d.get("message") or {}
                            if msg.get("content"):
                                content_parts.append(msg["content"])
                            if msg.get("thinking"):
                                thinking_parts.append(msg["thinking"])
                            if d.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
                    else:
                        continue
                    break
        full = "".join(content_parts).strip()
        if not full:
            full = "".join(thinking_parts).strip()
        return full or None
    except Exception:
        pass
    return None


def _ollama_json(prompt: str, model: str = _OLLAMA_MODEL) -> dict | None:
    """Send a prompt to Ollama and parse the response as JSON."""
    resp = _ollama_chat([{"role": "user", "content": prompt}], model=model)
    if not resp:
        return None
    resp = resp.strip()
    # Strip markdown code fences if present
    if resp.startswith("```"):
        resp = resp.split("\n", 1)[-1]
        resp = resp.rsplit("```", 1)[0]
        resp = resp.strip()
    try:
        return json.loads(resp)
    except json.JSONDecodeError:
        return None


def _ollama_embed(text: str) -> list[float] | None:
    """Generate an embedding vector via Ollama (nomic-embed-text)."""
    try:
        import httpx

        resp = httpx.post(
            f"{_OLLAMA_BASE}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text[:2048]},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("embedding")
    except Exception:
        pass
    # Fallback to sentence-transformers if installed
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text[:2048]).tolist()
    except ImportError:
        pass
    return None


def _open_rag_db(db_path: Path) -> sqlite3.Connection:
    """Open a connection with sqlite-vec loaded and foreign keys on."""
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ==========================================
# 3. WEB SEARCH HELPER (DuckDuckGo)
# ==========================================
def _web_search(query: str, max_results: int = 5) -> list[str]:
    """Search DuckDuckGo and return formatted result snippets."""
    try:
        # The package was renamed: duckduckgo_search → ddgs
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                f"[Web] {r['title']}: {r['body'][:500]}"
                for r in results
                if r.get("body")
            ]
    except ImportError:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                return [
                    f"[Web] {r['title']}: {r['body'][:500]}"
                    for r in results
                    if r.get("body")
                ]
        except Exception as e2:
            return [f"[Web] Search error: {e2}"]
    except Exception as e:
        return [f"[Web] Search error: {e}"]


# ==========================================
# 4. GRAPH NODES
# ==========================================

# --- Entry: Classify the query ---
def classify_node(state: QueryEngineState):
    """
    Use Ollama to determine action_type ('answer_q' | 'summarize_generate')
    and whether the query requires calculation.
    """
    query = state.get("query", "").strip().lower()
    if not query:
        return {"action_type": "answer_q", "require_calculation": False}

    # ── Keyword-based classification (fast, reliable with small models) ──
    summary_keywords = [
        "summarise", "summarize", "summary", "summarisation", "summarization",
        "all notes", "all my notes", "all documents", "everything",
        "study guide", "study material", "flashcards", "flash cards",
        "revision notes", "key points", "important points",
        "generate", "create notes",
    ]
    calc_keywords = [
        "calculate", "computation", "compute", "solve", "math",
        "equation", "formula", "numerical", "arithmetic",
        "sum", "average", "mean", "median", "standard deviation",
    ]

    is_summary = any(kw in query for kw in summary_keywords)
    is_calc = any(kw in query for kw in calc_keywords)

    # Use keyword result directly; no LLM fallback needed for such a
    # small model — keyword matching is more reliable with tinyllama.
    return {
        "action_type": "summarize_generate" if is_summary else "answer_q",
        "require_calculation": is_calc,
    }


# --- Track 1: Answer Question Branch ---
def answer_q_node(state: QueryEngineState):
    """Pass-through node marking the start of the answer-q branch."""
    return {}


# The Parallel "Get Context" Box (Fires simultaneously)
def web_search_node(state: QueryEngineState):
    """Web search via DuckDuckGo (disabled by default, gated by web_search_toggle_router)."""
    query = state.get("query", "")
    if not query:
        return {"retrieved_contexts": []}
    results = _web_search(query)
    return {"retrieved_contexts": results}


def vector_search_node(state: QueryEngineState):
    """
    Semantic vector search using sqlite-vec cosine-similarity lookup.
    Uses Ollama nomic-embed-text, with sentence-transformers fallback.
    """
    query = state.get("query", "").strip()
    vessel_path = state.get("vessel_path", "")
    if not query or not vessel_path:
        return {"retrieved_contexts": []}

    db_path = Path(vessel_path) / "AI" / ".sys" / "vessel_rag.db"
    if not db_path.exists():
        return {"retrieved_contexts": ["[Vector Search] DB not found"]}

    embedding = _ollama_embed(query)
    if embedding is None:
        return {"retrieved_contexts": ["[Vector Search] No embedding model available"]}

    try:
        conn = _open_rag_db(db_path)
        cursor = conn.cursor()

        rows = cursor.execute(
            """
            SELECT v.rowid, d.title, d.text_chunk, v.distance
            FROM v_document_embeddings v
            JOIN documents d ON d.id = v.rowid
            WHERE v.embedding MATCH ? AND v.k = 5
            ORDER BY v.distance
            """,
            (json.dumps(embedding),),
        ).fetchall()
        conn.close()

        contexts = [
            f"[Vector] {r[1]}: {r[2][:300]} (dist={r[3]:.4f})" for r in rows
        ]
        if not contexts:
            contexts = ["[Vector Search] No similar documents found"]

        return {"retrieved_contexts": contexts}

    except Exception as e:
        return {"retrieved_contexts": [f"[Vector Search] Error: {e}"]}


def keyword_search_node(state: QueryEngineState):
    """
    BM25 keyword search via SQLite FTS5.
    Uses the bm25_search() helper from modules/__init__.py
    """
    query = state.get("query", "").strip()
    vessel_path = state.get("vessel_path", "")
    if not query or not vessel_path:
        return {"retrieved_contexts": []}

    db_path = Path(vessel_path) / "AI" / ".sys" / "vessel_rag.db"
    if not db_path.exists():
        return {"retrieved_contexts": ["[BM25] No RAG database found for this vessel."]}

    results = bm25_search(db_path, query, top_k=10)

    if not results:
        return {"retrieved_contexts": ["[BM25] No keyword matches found."]}

    contexts = [
        f"[BM25] {r['title']}: {r['text_chunk'][:300]} (rank={r['rank']:.4f})"
        for r in results
    ]
    return {"retrieved_contexts": contexts}


def extract_text_node(state: QueryEngineState):
    """Aggregate parallel contexts — the contexts are already accumulated via operator.add."""
    return {}


# Code Generation Node — for calculations, data processing, file I/O, etc.
def generate_py_script_node(state: QueryEngineState):
    """
    Use Ollama to generate and run Python code for any task that
    requires computation, data processing, file output, or other
    operations not already built into the system.
    """
    query = state.get("query", "")
    contexts = state.get("retrieved_contexts", [])
    context_text = "\n".join(contexts) if contexts else "No context available."

    prompt = f"""You are a Python code generator. Write a Python script that fulfills the user request using only standard library modules.

The script can:
- Perform calculations and numerical analysis
- Process, transform, or filter data
- Generate files or formatted output
- Fetch web content (via urllib)
- Parse HTML/JSON/CSV/XML
- Do string manipulation and text generation

Requirements:
1. Print the final output to stdout
2. Use only stdlib (no pip installs)
3. Handle errors gracefully with try/except
4. Be self-contained (no external files needed unless you create them)

Query: {query}
Context: {context_text}

Output ONLY the raw Python code, no explanations, no markdown fences."""

    # Include conversational context so the code generator understands
    # the broader conversation (e.g. follow-up refinements, corrections).
    messages = list(state.get("chat_history", []))
    messages.append({"role": "user", "content": prompt})
    code = _ollama_chat(messages, timeout=120)
    if not code:
        return {"generated_script_output": "Failed to generate calculation script."}

    # Strip markdown code fences if present
    if code.startswith("```"):
        code = code.split("\n", 1)[-1]
        code = code.rsplit("```", 1)[0]
        code = code.strip()

    # Execute the generated code
    try:
        import subprocess

        result = subprocess.run(
            [_sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return {"generated_script_output": output or "Script produced no output."}
    except subprocess.TimeoutExpired:
        return {"generated_script_output": "Script execution timed out."}
    except Exception as e:
        return {"generated_script_output": f"Script execution error: {e}"}


# --- Track 2: Summarize / Generate Questions Branch ---
_ALL_KEYWORDS = {
    "all notes", "all my notes", "all documents", "all my documents",
    "everything", "the whole", "entire", "all content", "whole thing",
}
_STOP_WORDS = {
    "summarise", "summarize", "summary", "notes", "documents",
    "about", "for", "the", "a", "an", "of", "to", "in", "on", "at",
    "by", "with", "from", "my", "your", "its", "our", "their",
    "please", "can", "could", "would", "make", "create", "give",
    "generate", "need", "want", "get", "do", "does", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had",
    "i", "me", "we", "you", "he", "she", "it", "they", "them",
    "some", "any", "all", "each", "every", "both", "few", "more",
    "most", "other", "into", "over", "after", "before", "between",
    "this", "that", "these", "those",
}


def parse_summarize_query_node(state: QueryEngineState):
    """
    Determine whether the query targets *all* content or a specific topic.
    Returns ``topic_keyword`` — empty string means "fetch all documents",
    a non-empty string means "search documents by this topic".

    Uses keyword matching (no LLM call) — fast and reliable with small models.
    """
    query = state.get("query", "")

    # Detect "all" mode
    q_lower = query.strip().lower()
    for phrase in _ALL_KEYWORDS:
        if phrase in q_lower:
            return {"topic_keyword": ""}

    # Extract topic keyword: remove stop words, take remaining words
    words = q_lower.split()
    meaningful = [w.strip(",.!?;:'\"") for w in words if w not in _STOP_WORDS and len(w) > 2]
    topic = " ".join(meaningful[:5]).strip()
    return {"topic_keyword": topic}


def check_if_relevant_node(state: QueryEngineState):
    """Use Ollama to grade whether the retrieved context is relevant to the query."""
    query = state.get("query", "")
    contexts = state.get("retrieved_contexts", [])
    context_text = "\n".join(contexts) if contexts else "No context available."

    prompt = f"""You are a relevance grader for a RAG system. Determine if the retrieved context is relevant to the user query.

Query: {query}

Context:
{context_text}

Return a JSON object with:
- "is_relevant": true if the context helps answer the query or generate the requested study material, false if completely unrelated

Respond with ONLY the JSON object."""

    result = _ollama_json(prompt)
    if result is None:
        return {"is_relevant": True}
    return {"is_relevant": result.get("is_relevant", True)}


# --- New nodes for the two summarize-search strategies ---
def get_all_documents_node(state: QueryEngineState):
    """Fetch ALL documents — no search, no ranking. Returns everything."""
    vessel_path = state.get("vessel_path", "")
    if not vessel_path:
        return {"retrieved_contexts": ["[All Docs] No vessel path."]}

    db_path = Path(vessel_path) / "AI" / ".sys" / "vessel_rag.db"
    if not db_path.exists():
        return {"retrieved_contexts": ["[All Docs] DB not found."]}

    docs = get_all_documents(db_path)
    if not docs:
        return {"retrieved_contexts": ["[All Docs] No documents in the database."]}

    contexts = [
        f"[Doc {d['id']}] {d['title']}: {d['text_chunk']}" for d in docs
    ]
    return {"retrieved_contexts": contexts}


def search_by_topic_node(state: QueryEngineState):
    """Run both tag-search and vector-search on the extracted topic keyword."""
    vessel_path = state.get("vessel_path", "")
    topic = state.get("topic_keyword", "")
    if not vessel_path or not topic:
        return {"retrieved_contexts": ["[Topic] No vessel path or keyword."]}

    db_path = Path(vessel_path) / "AI" / ".sys" / "vessel_rag.db"
    if not db_path.exists():
        return {"retrieved_contexts": ["[Topic] DB not found."]}

    contexts: list[str] = []

    # 1. Tag search — match documents whose tags contain the keyword
    tagged = tag_search(db_path, [topic])
    if tagged:
        for d in tagged:
            contexts.append(f"[Tag] {d['title']}: {d['text_chunk'][:300]}")
    else:
        contexts.append("[Tag Search] No documents found for this topic.")

    # 2. Vector search — semantic similarity on the keyword
    embedding = _ollama_embed(topic)
    if embedding is not None:
        try:
            conn = _open_rag_db(db_path)
            cursor = conn.cursor()
            rows = cursor.execute(
                """
                SELECT v.rowid, d.title, d.text_chunk, v.distance
                FROM v_document_embeddings v
                JOIN documents d ON d.id = v.rowid
                WHERE v.embedding MATCH ? AND v.k = 5
                ORDER BY v.distance
                """,
                (json.dumps(embedding),),
            ).fetchall()
            conn.close()
            for r in rows:
                contexts.append(f"[Vector] {r[1]}: {r[2][:300]} (dist={r[3]:.4f})")
            if not rows:
                contexts.append("[Vector Search] No semantically similar documents found.")
        except Exception as e:
            contexts.append(f"[Vector Search] Error: {e}")
    else:
        contexts.append("[Vector Search] No embedding model available.")

    return {"retrieved_contexts": contexts}


# --- Final Target Node ---
def generate_answer_node(state: QueryEngineState):
    """
    Use Ollama to produce the final answer by synthesising
    all retrieved contexts (vector, BM25, web, tags) with the original query.
    """
    query = state.get("query", "")
    contexts = state.get("retrieved_contexts", [])
    calc_output = state.get("generated_script_output", "")

    context_text = (
        "\n\n".join(contexts)
        if contexts
        else "No documents were found in the knowledge base."
    )

    if calc_output:
        context_text += f"\n\nCalculation result:\n{calc_output}"

    action_type = state.get("action_type", "answer_q")

    if action_type == "summarize_generate":
        prompt = f"""DOCUMENTS
{context_text}

USER REQUEST: {query}

INSTRUCTION: Write a summary of the documents above. Start with the summary itself. No document listings. No meta-commentary."""  # noqa: E501
    else:
        prompt = f"""CONTEXT
{context_text}

QUESTION
{query}

INSTRUCTION: Answer using the context above. If it lacks the information, say so. Be specific."""

    # Build full message list with conversational history
    messages = list(state.get("chat_history", []))
    messages.append({"role": "user", "content": prompt})
    answer = _ollama_chat(messages, timeout=120)
    if not answer:
        answer = (
            "I couldn't generate a response. The Ollama service may not be running.\n"
            "Start it with `ollama serve` in your terminal."
        )

    return {"final_answer": answer.strip()}


# --- Answer Quality Check & Refinement Loop ---
def quality_check_node(state: QueryEngineState):
    """
    Evaluate the generated answer for quality.
    Returns a score (0-10) and specific improvement feedback.
    If score is low, the refinement loop will improve the answer.
    """
    query = state.get("query", "")
    answer = state.get("final_answer", "")
    attempts = state.get("refinement_attempts", 0)
    max_attempts = state.get("max_refinements", 3)

    # If already at max attempts, skip evaluation — just pass through
    if attempts >= max_attempts:
        return {
            "answer_quality_score": 10,
            "refinement_feedback": "",
        }

    if not answer:
        return {
            "answer_quality_score": 0,
            "refinement_feedback": "No answer was generated.",
        }

    prompt = f"""You are an answer quality grader. Evaluate this answer on three criteria, each 0-10:

Query: {query}

Answer: {answer}

Return ONLY a JSON object:
{{
  "completeness": <0-10>,
  "accuracy": <0-10>,
  "clarity": <0-10>,
  "feedback": "<one specific thing to improve>"
}}"""

    result = _ollama_json(prompt)
    if result is None:
        # If grading fails, assume it's fine to avoid infinite loops
        return {"answer_quality_score": 10, "refinement_feedback": ""}

    completeness = result.get("completeness", 5)
    accuracy = result.get("accuracy", 5)
    clarity = result.get("clarity", 5)
    overall = round((completeness + accuracy + clarity) / 3)
    feedback = result.get("feedback", "")

    return {
        "answer_quality_score": overall,
        "refinement_feedback": feedback,
    }


def refine_answer_node(state: QueryEngineState):
    """
    Improve the answer based on quality check feedback.
    Then increment the refinement counter so the loop can terminate.
    """
    query = state.get("query", "")
    prev_answer = state.get("final_answer", "")
    feedback = state.get("refinement_feedback", "")
    contexts = state.get("retrieved_contexts", [])
    attempts = state.get("refinement_attempts", 0) + 1
    context_text = "\n\n".join(contexts) if contexts else "No context available."

    prompt = f"""You are improving a previous answer based on feedback.

User Query: {query}

Context:
{context_text}

Previous Answer:
{prev_answer}

Feedback to address:
{feedback}

Provide an improved, thorough answer that addresses the feedback above."""

    # Preserve conversational context during refinement
    messages = list(state.get("chat_history", []))
    messages.append({"role": "user", "content": prompt})
    improved = _ollama_chat(messages, timeout=120)
    if not improved:
        improved = prev_answer  # keep previous if refinement fails

    return {
        "final_answer": improved.strip(),
        "refinement_attempts": attempts,
    }


# ==========================================
# 5. ROUTER CONDITIONAL EDGES
# ==========================================


def initial_action_router(state: QueryEngineState) -> str:
    """Route to answer_q or summarize_generate based on classify_node output."""
    if state.get("action_type") == "summarize_generate":
        return "route_to_summarizer"
    return "route_to_answer_q"


def summarize_router(state: QueryEngineState) -> str:
    """
    After parse_summarize_query_node: route based on ``topic_keyword``.
    Empty string → fetch ALL documents.
    Non-empty string → search by that topic (tag + vector).
    """
    if state.get("topic_keyword", ""):
        return "route_to_search_by_topic"
    return "route_to_all_docs"


def web_search_toggle_router(state: QueryEngineState) -> List[str]:
    """
    Parallel fan-out: vector and keyword always fire.
    Web search is added only when the user enables it.
    """
    activated_nodes = ["vector_search_node", "keyword_search_node"]
    if state.get("web_search_enabled", False):
        activated_nodes.append("web_search_node")
    return activated_nodes


def calculation_router(state: QueryEngineState) -> str:
    if state.get("require_calculation", False):
        return "route_to_calc_runner"
    return "skip_to_answer_generation"


def relevance_router(state: QueryEngineState) -> str:
    if state.get("is_relevant", True):
        return "route_to_answer_generation"
    return "skip_to_end"


def quality_router(state: QueryEngineState) -> str:
    """
    After quality_check_node: if score >= 7 or max refinements reached → END.
    Otherwise → refine_answer_node for another pass.
    """
    score = state.get("answer_quality_score", 10)
    attempts = state.get("refinement_attempts", 0)
    max_attempts = state.get("max_refinements", 3)

    if score >= 7 or attempts >= max_attempts:
        return "route_to_end"
    return "route_to_refine"


# ==========================================
# 6. BUILD THE QUERY ENGINE GRAPH
# ==========================================
workflow = StateGraph(QueryEngineState)

# Entry
workflow.add_node("classify_node", classify_node)

# Track 1: Answer Question
workflow.add_node("answer_q_node", answer_q_node)
workflow.add_node("web_search_node", web_search_node)
workflow.add_node("vector_search_node", vector_search_node)
workflow.add_node("keyword_search_node", keyword_search_node)
workflow.add_node("extract_text_node", extract_text_node)
workflow.add_node("generate_py_script_node", generate_py_script_node)

# Track 2: Summarize / Generate
workflow.add_node("parse_summarize_query_node", parse_summarize_query_node)
workflow.add_node("get_all_documents_node", get_all_documents_node)
workflow.add_node("search_by_topic_node", search_by_topic_node)
workflow.add_node("check_if_relevant_node", check_if_relevant_node)

# Final
workflow.add_node("generate_answer_node", generate_answer_node)

# Answer refinement loop
workflow.add_node("quality_check_node", quality_check_node)
workflow.add_node("refine_answer_node", refine_answer_node)

# 1. START → classify
workflow.add_edge(START, "classify_node")

# 2. classify → main fork
workflow.add_conditional_edges(
    "classify_node",
    initial_action_router,
    {
        "route_to_answer_q": "answer_q_node",
        "route_to_summarizer": "parse_summarize_query_node",
    },
)

# 3. Track 1: Answer Q → parallel search nodes
workflow.add_conditional_edges(
    "answer_q_node",
    web_search_toggle_router,
    ["web_search_node", "vector_search_node", "keyword_search_node"],
)

workflow.add_edge("web_search_node", "extract_text_node")
workflow.add_edge("vector_search_node", "extract_text_node")
workflow.add_edge("keyword_search_node", "extract_text_node")

# 4. Track 1: Extract → calculation fork → answer
workflow.add_conditional_edges(
    "extract_text_node",
    calculation_router,
    {
        "route_to_calc_runner": "generate_py_script_node",
        "skip_to_answer_generation": "generate_answer_node",
    },
)
workflow.add_edge("generate_py_script_node", "generate_answer_node")

# 5. Track 2: parse_summarize_query → (all-docs | topic-search) → answer
workflow.add_conditional_edges(
    "parse_summarize_query_node",
    summarize_router,
    {
        "route_to_all_docs": "get_all_documents_node",
        "route_to_search_by_topic": "search_by_topic_node",
    },
)

workflow.add_edge("get_all_documents_node", "generate_answer_node")
workflow.add_edge("search_by_topic_node", "check_if_relevant_node")

workflow.add_conditional_edges(
    "check_if_relevant_node",
    relevance_router,
    {
        "route_to_answer_generation": "generate_answer_node",
        "skip_to_end": END,
    },
)

# 6. Answer → end (quality loop disabled for tinyllama — small models
#    cannot reliably grade or refine, and the extra calls worsen output)
workflow.add_edge("generate_answer_node", END)

app = workflow.compile()
