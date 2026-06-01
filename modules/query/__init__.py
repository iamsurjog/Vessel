import operator
from typing import Annotated, List, TypedDict
from langgraph.graph import START, END, StateGraph

# ==========================================
# 1. THE QUERY ENGINE STATE
# ==========================================
class QueryEngineState(TypedDict):
    query: str
    action_type: str            # 'answer_q' or 'summarize_generate'
    web_search_enabled: bool
    require_calculation: bool
    is_relevant: bool
    
    # 'operator.add' aggregates multi-channel search results seamlessly
    retrieved_contexts: Annotated[List[str], operator.add]
    generated_script_output: str
    final_answer: str


# ==========================================
# 2. GRAPH NODE STUBS
# ==========================================

# --- Track 1: Answer Question Branch ---
async def answer_q_node(state: QueryEngineState):
    print("🤖 [Answer Q Node] Processing question intent...")
    return {}

# The Parallel "Get Context" Box (Fires simultaneously)
async def web_search_node(state: QueryEngineState):
    print("🔍 [Get Context] Running Web Search...")
    return {"retrieved_contexts": ["Web Context Data"]}

async def vector_search_node(state: QueryEngineState):
    print("🧬 [Get Context] Running Vector Embed Search...")
    return {"retrieved_contexts": ["Vector DB Context Data"]}

async def keyword_search_node(state: QueryEngineState):
    print("🔑 [Get Context] Running Keyword Search...")
    return {"retrieved_contexts": ["Keyword/Tag Match Data"]}

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
    # Dynamic Fan-Out: Vector and Keyword search always run, Web Search is optional
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

# Register all layout blocks
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

# --- WIRE THE SWITCHBOARDS ---

# 1. Main entry fork (Action?)
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
    # Directly lists the potential parallel target nodes
    ["web_search_node", "vector_search_node", "keyword_search_node"]
)

# Map the parallel search tracks back into the text extractor sync point
workflow.add_edge("web_search_node", "extract_text_node")
workflow.add_edge("vector_search_node", "extract_text_node")
workflow.add_edge("keyword_search_node", "extract_text_node")

# 3. Track 1: Calculation Fork (Require Calc?)
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

# Check if relevant split
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
workflow.add_edge("answer_q_node", "web_search_node")
workflow.add_edge("answer_q_node", "vector_search_node")
workflow.add_edge("answer_q_node", "keyword_search_node")