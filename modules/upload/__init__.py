import operator
from typing import Annotated, List, TypedDict
from langgraph.graph import START, END, StateGraph

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
# 2. GRAPH NODE STUBS
# ==========================================
# Phase 1: Conversion & Extraction Nodes
async def convert_to_pdf_node(state: IngestionState):
    return {"db_logs": ["Converted PPT/Doc to PDF"]}

async def extract_text_node(state: IngestionState):
    return {"extracted_text": "Clean parsed text content here..."}

async def generate_description_node(state: IngestionState):
    return {"description": "Vision/Audio LLM analysis description...", "extracted_text": "Extracted media metadata..."}

# Phase 2: Downstream Storage Nodes (Run in Parallel)
async def create_and_store_vec_embeddings(state: IngestionState):
    # Hits sqlite-vec table
    return {"db_logs": ["Stored vector embedding."]}

async def store_txt_as_file(state: IngestionState):
    # Saves to path/AI/content/file.txt
    return {"db_logs": ["Saved raw text chunk to file."]}

async def create_and_store_tags(state: IngestionState):
    # Hits relational tags junction table
    return {"db_logs": ["Created and linked search tags."]}


# ==========================================
# 3. ROUTER CONDITIONAL EDGES
# ==========================================
def filetype_router(state: IngestionState) -> str:
    f_type = state["file_type"].lower()
    
    if f_type in ["ppt", "doc"]:
        return "route_to_converter"
    elif f_type in ["pdf", "txt", "html"]:
        return "route_to_extractor"

    elif f_type in ["image", "video"]:
        return "route_to_descriptor"
    
    return "route_to_extractor"


# ==========================================
# 4. BUILD THE GRAPH
# ==========================================
workflow = StateGraph(IngestionState)

# Register all layout blocks
workflow.add_node("convert_to_pdf_node", convert_to_pdf_node)
workflow.add_node("extract_text_node", extract_text_node)
workflow.add_node("generate_description_node", generate_description_node)

workflow.add_node("create_and_store_vec_embeddings", create_and_store_vec_embeddings)
workflow.add_node("store_txt_as_file", store_txt_as_file)
workflow.add_node("create_and_store_tags", create_and_store_tags)

# --- WIRE THE SWITCHBOARD ---
# Start node branches out depending on what type of file was uploaded
workflow.add_conditional_edges(
    START,
    filetype_router,
    {
        "route_to_converter": "convert_to_pdf_node",
        "route_to_extractor": "extract_text_node",
        "route_to_descriptor": "generate_description_node"
    }
)

# Intermediary steps route back into main extractor block
workflow.add_edge("convert_to_pdf_node", "extract_text_node")

# --- THE FAN-OUT PIPELINE ---
# Once text extraction/processing finishes, trigger all 3 storage blocks simultaneously
workflow.add_edge("extract_text_node", "create_and_store_vec_embeddings")
workflow.add_edge("extract_text_node", "store_txt_as_file")
workflow.add_edge("extract_text_node", "create_and_store_tags")

workflow.add_edge("generate_description_node", "create_and_store_vec_embeddings")
workflow.add_edge("generate_description_node", "store_txt_as_file")
workflow.add_edge("generate_description_node", "create_and_store_tags")

# --- THE FAN-IN ---
# Map everything to terminate gracefully after database writes finish
workflow.add_edge("create_and_store_vec_embeddings", END)
workflow.add_edge("store_txt_as_file", END)
workflow.add_edge("create_and_store_tags", END)

app = workflow.compile()

