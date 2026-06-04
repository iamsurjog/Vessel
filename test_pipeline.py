#!/usr/bin/env python3
"""
Diagnostic test for the query pipeline.
Run with:  python3 test_pipeline.py /path/to/vessel 'summarize all my notes'
"""

import json
import sys
import os
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import get_all_documents, tag_search, bm25_search
from modules.query import (
    app,
    QueryEngineState,
    _ollama_chat,
    _llm_chat,
    _llm_embed,
    _OLLAMA_MODEL,
    _OLLAMA_BASE,
)


def db_path_from_vessel(vessel_path: str) -> Path:
    return Path(vessel_path) / "AI" / ".sys" / "vessel_rag.db"


def step(label: str, obj):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    if isinstance(obj, str):
        print(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            val = str(v)
            if len(val) > 500:
                val = val[:500] + f"\n  ... (truncated, {len(str(v))} chars)"
            print(f"  {k}: {val}")
    elif isinstance(obj, list):
        print(f"  count: {len(obj)}")
        for i, item in enumerate(obj[:5]):
            print(f"  [{i}] {str(item)[:300]}")
        if len(obj) > 5:
            print(f"  ... and {len(obj)-5} more")
    else:
        print(f"  {obj}")


def main():
    if len(sys.argv) < 3:
        vessel_path = input("Vessel path: ").strip()
        query = input("Query: ").strip() or "summarize all my notes"
    else:
        vessel_path = sys.argv[1]
        query = sys.argv[2]

    dbp = db_path_from_vessel(vessel_path)

    # ── 1. Check the database ────────────────────────────────────────
    if not dbp.exists():
        print(f"\n❌ DB not found at {dbp}")
        sys.exit(1)
    print(f"\n✅ DB found at {dbp}")

    # List all documents
    docs = get_all_documents(dbp)
    step(f"All documents in DB ({len(docs)} total)", docs[:10] if docs else "EMPTY")

    # ── 2. Run the pipeline with a monkey-patched _ollama_chat ───────
    # We'll capture the exact prompt sent (the dispatch goes through
    # _llm_chat → _ollama_chat for the default ollama provider)
    last_prompt = [""]

    original_chat = _ollama_chat

    def capturing_chat(messages, model=_OLLAMA_MODEL, timeout=120):
        last_prompt[0] = json.dumps(messages, indent=2)
        print(f"\n{'─'*70}")
        print("  PROMPT SENT TO OLLAMA (via _llm_chat dispatch):")
        print(f"{'─'*70}")
        print(last_prompt[0])
        print(f"{'─'*70}")
        result = original_chat(messages, model, timeout)
        print(f"\n  RAW RESPONSE ({len(result or '')} chars):")
        print(f"  {result}")
        return result

    import modules.query as qm
    qm._ollama_chat = capturing_chat

    # ── 3. Invoke the pipeline ──────────────────────────────────────
    print(f"\n{'#'*70}")
    print(f"  RUNNING PIPELINE: {query}")
    print(f"{'#'*70}")

    provider_config = {
        "provider": "ollama",
        "ollama_model": "tinyllama:1.1b",
    }

    initial_state = {
        "query": query,
        "vessel_path": vessel_path,
        "web_search_enabled": False,
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
        "chat_history": [],
        "provider_config": provider_config,
    }

    try:
        result = app.invoke(initial_state)
        answer = result.get("final_answer", "")
        action = result.get("action_type", "?")
        topic = result.get("topic_keyword", "?")
        contexts = result.get("retrieved_contexts", [])
        pconf = result.get("provider_config", {})

        print(f"\n{'#'*70}")
        step("PIPELINE RESULT", {
            "action_type": action,
            "topic_keyword": topic,
            "provider": pconf.get("provider", "?"),
            "contexts_count": len(contexts),
            "contexts_sample": contexts[:3] if contexts else "(empty)",
            "final_answer": answer,
        })
        print(f"{'#'*70}")
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        import traceback
        traceback.print_exc()

    # ── 4. Also test Ollama directly with a minimal prompt ───────────
    print(f"\n{'#'*70}")
    print("  DIRECT OLLAMA TEST (minimal prompt, no pipeline)")
    print(f"{'#'*70}")

    context_sample = "\n".join(
        f"[Doc {d['id']}] {d['title']}: {d['text_chunk'][:200]}"
        for d in docs[:3]
    ) if docs else "(no docs)"

    minimal_prompt = f"""DOCUMENTS
{context_sample}

USER REQUEST: {query}

INSTRUCTION: Answer the user's request directly using the documents above. If the user asked for a summary, cover the main points from every document. Do not add meta-commentary about yourself or the instructions."""

    messages = [
        {"role": "system", "content": "Answer concisely. Use the context directly. No commentary."},
        {"role": "user", "content": minimal_prompt},
    ]
    print(f"\n  MINIMAL PROMPT:\n{json.dumps(messages, indent=2)}")
    direct_response = original_chat(messages, timeout=120)
    print(f"\n  DIRECT RESPONSE:\n  {direct_response}")


if __name__ == "__main__":
    main()
