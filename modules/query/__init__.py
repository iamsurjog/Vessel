import json
import operator
from pathlib import Path
from typing import Annotated, List, TypedDict
from langgraph.graph import START, END, StateGraph
import sqlite3
import sqlite_vec

# The bm25_search function lives in modules/__init__.py so it's importable
# from anywhere, but the query graph also uses it directly.
from modules import bm25_search


# ==========================================
# 1. THE QUERY ENGINE STATE
# ==========================================
class QueryEngineState(TypedDict):
    query: str
    action_type: str            # 'answer_q' or 'summarize_generate'
    web_search_enabled: bool
    require_calculation: bool
    is_relevant: bool
    vessel_path: str            # added — so BM25 / vector nodes know where the DB is

    # 'operator.add' aggregates multi-channel search results seamlessly
    retrieved_contexts: Annotated[List[str], operator.add]
    generated_script_output: str
    final_answer: str


# ==========================================
# 2. GRAPH NODES
# ==========================================

# --- Track 1: Answer Question Branch ---
async def answer_q_node(state: QueryEngineState):
    print("🤖 [Answer Q Node] Processing question intent...")
    return {}


# The Parallel "Get Context" Box (Fires simultaneously)
async def web_search_node(state: QueryEngineState):
    print("🔍 [Get Context] Running Web Search...")
    # Web search is left as a stub — wire up your own search API here.
    return {"retrieved_contexts": ["Web Context Data"]}


async def vector_search_node(state: QueryEngineState):
    """
    Semantic vector search using sqlite-vec cosine-similarity lookup.
    """
    query = state.get("query", "").strip()
    vessel_path = state.get("vessel_path", "")
    if not query or not vessel_path:
        return {"retrieved_contexts": []}

    db_path = Path(vessel_path) / "AI" / ".sys" / "vessel_rag.db"
    if not db_path.exists():
        return {"retrieved_contexts": ["[Vector Search] DB not found"]}

    # To run vector search we need an embedding model.
    # Try the same two strategies as the upload pipeline.
    embedding = None

    try:
        import httpx
        resp = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": query[:2048]},
            timeout=10,
        )
        if resp.status_code == 200:
            embedding = resp.json().get("embedding")
    except Exception:
        pass

    if embedding is None:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embedding = model.encode(query[:2048]).tolist()
        except ImportError:
            pass

    if embedding is None:
        return {"retrieved_contexts": ["[Vector Search] No embedding model available"]}

    # Query sqlite-vec for top-5 similar documents
    try:
        conn = sqlite3.connect(str(db_path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        cursor = conn.cursor()

        rows = cursor.execute(
            """
            SELECT d.title, d.text_chunk, distance
            FROM v_document_embeddings
            JOIN documents d ON d.id = v_document_embeddings.rowid
            WHERE v_document_embeddings MATCH ?
              AND k = 5
            ORDER BY distance
            """,
            (json.dumps(embedding),),
        ).fetchall()
        conn.close()

        contexts = [
            f"[Vector] {r[0]}: {r[1][:300]} (dist={r[2]:.4f})"
            for r in rows
        ]
        if not contexts:
            contexts = ["[Vector Search] No similar documents found"]

        return {"retrieved_contexts": contexts}

    except Exception as e:
        return {"retrieved_contexts": [f"[Vector Search] Error: {e}"]}


async def keyword_search_node(state: QueryEngineState):
    """
    BM25 keyword search via SQLite FTS5.

    Actually runs the search — not a stub.
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


# Extract Text Node aggregates the parallel streams
async def extract_text_node(state: QueryEngineState):
    print("📄 [Extract Text] Compiling and cleaning retrieved contexts...")
    return {}


# Calculation Sub-Branch Nodes
async def generate_py_script_node(state: QueryEngineState):
    print("💻 [Calc Route] Writing and running Python execution script...")
    return {"generated_script_output": "Executed script calculation output..."}


# --- Track 2: Summarize / Generate Questions Branch ---
async def summarize_generate_node(state: QueryEngineState):
    print("📝 [Summarize/Generate Node] Processing document task...")
    return {}


async def get_select_data_by_tag_or_folder(state: QueryEngineState):
    print("📂 [Data Loader] Pulling records matching Tag/Folder configuration...")
    return {"retrieved_contexts": ["Raw Tagged/Folder Data Context"]}


async def check_if_relevant_node(state: QueryEngineState):
    print("⚖️  [Evaluator] Grading context relevance...")
    return {"is_relevant": True}


# --- Final Target Node ---
async def generate_answer_node(state: QueryEngineState):
    print("✨ [Generate Answer] Formatting the final output response for user.")
    return {"final_answer": "Here is your data-backed response."}


# ==========================================
# 3. ROUTER CONDITIONAL EDGES
# ==========================================

def initial_action_router(state: QueryEngineState) -> str:
    if state["action_type"] == "summarize_generate":
        return "route_to_summarizer"
    return "route_to_answer_q"


def web_search_toggle_router(state: QueryEngineState) -> List[str]:
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


# ==========================================
# 4. BUILD THE QUERY ENGINE GRAPH
# ==========================================
workflow = StateGraph(QueryEngineState)

workflow.add_node("answer_q_node", answer_q_node)
workflow.add_node("web_search_node", web_search_node)
workflow.add_node("vector_search_node", vector_search_node)
workflow.add_node("keyword_search_node", keyword_search_node)
workflow.add_node("extract_text_node", extract_text_node)
workflow.add_node("generate_py_script_node", generate_py_script_node)

workflow.add_node("summarize_generate_node", summarize_generate_node)
workflow.add_node("get_select_data_by_tag_or_folder", get_select_data_by_tag_or_folder)
workflow.add_node("check_if_relevant_node", check_if_relevant_node)

workflow.add_node("generate_answer_node", generate_answer_node)

# 1. Main entry fork
workflow.add_conditional_edges(
    START,
    initial_action_router,
    {
        "route_to_answer_q": "answer_q_node",
        "route_to_summarizer": "summarize_generate_node"
    }
)

# 2. Track 1: Get Context Parallel Fan-Out
workflow.add_conditional_edges(
    "answer_q_node",
    web_search_toggle_router,
    ["web_search_node", "vector_search_node", "keyword_search_node"]
)

workflow.add_edge("web_search_node", "extract_text_node")
workflow.add_edge("vector_search_node", "extract_text_node")
workflow.add_edge("keyword_search_node", "extract_text_node")

# 3. Track 1: Calculation Fork
workflow.add_conditional_edges(
    "extract_text_node",
    calculation_router,
    {
        "route_to_calc_runner": "generate_py_script_node",
        "skip_to_answer_generation": "generate_answer_node"
    }
)
workflow.add_edge("generate_py_script_node", "generate_answer_node")

# 4. Track 2: Summarize / Tag Retrieval Pipeline
workflow.add_edge("summarize_generate_node", "get_select_data_by_tag_or_folder")
workflow.add_edge("get_select_data_by_tag_or_folder", "check_if_relevant_node")

workflow.add_conditional_edges(
    "check_if_relevant_node",
    relevance_router,
    {
        "route_to_answer_generation": "generate_answer_node",
        "skip_to_end": END
    }
)

# 5. Close Graph
workflow.add_edge("generate_answer_node", END)

app = workflow.compile()
