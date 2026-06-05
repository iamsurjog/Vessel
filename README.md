# Vessel

A local-first desktop knowledge workspace with AI-powered RAG (Retrieval-Augmented Generation). Everything runs on your machine — no cloud, no telemetry, no accounts. Write notes, store materials, and ask questions entirely offline.

Built with PySide6 (Qt6) and QML for the interface, LangGraph for the AI query pipeline, and sqlite-vec for vector search. Supports multiple AI providers (Ollama, OpenAI, Anthropic, Google) and optional DuckDuckGo web search.

**Features**
- **Droplets** — Markdown notes with a live editor and render mode
- **Materials** — Drag-and-drop file vault that indexes PDFs, images, videos, office docs, and more
- **AI Chat** — Conversational RAG over your notes and materials with BM25 + vector search
- **Tag Search** — Inverted-index document lookup
- **Calendar** — Simple per-vessel event tracking
- **PDF Viewer** — Built-in PDF rendering with Qt's PDF engine

## Installing

### Install

Pre-built binaries are available on the [Releases](https://github.com/iamsurjog/Vessel/releases) page. Download the archive for your platform, extract it, and run the executable.

### Build from Source

```bash
# Clone the repo
git clone https://github.com/iamsurjog/Vessel.git
cd vessel

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

> **Note:** Development targets Python 3.14. Nearby versions (3.12, 3.13) may work, but have not been tested.
