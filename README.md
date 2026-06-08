# Vessel

A local-first desktop knowledge workspace with AI-powered RAG (Retrieval-Augmented Generation). Everything runs on your machine — no cloud, no telemetry, no accounts. Write notes, store materials, and ask questions entirely offline.

Built with **PySide6 (Qt6)** and **QML** for the interface, **LangGraph** for the AI query pipeline, and **sqlite-vec** for vector search. Supports multiple AI providers (Ollama, OpenAI, Anthropic, Google) and optional DuckDuckGo web search.

---

## Table of Contents

- [Features](#features)
- [Installing](#installing)
  - [Pre-built Binaries](#pre-built-binaries)
  - [Build from Source](#build-from-source)
- [Usage](#usage)
  - [Vessels](#vessels)
  - [Droplets](#droplets)
  - [Materials](#materials)
  - [AI Chat](#ai-chat)
  - [Calendar](#calendar)
- [Architecture](#architecture)
  - [Upload Pipeline](#upload-pipeline)
  - [Query Pipeline](#query-pipeline)
  - [Database Schema](#database-schema)
- [AI Providers](#ai-providers)
- [Configuration](#configuration)
- [Tech Stack](#tech-stack)
- [Contributing](#contributing)
- [License](#license)

---

## Features

### Vessel Management
- **Create, open, delete** named workspaces ("vessels") — each vessel is an isolated directory with its own notes, files, and RAG database.
- **Multi-vessel registry** — persistent history of all your vessels stored at `~/.config/vessel/vessels_history.json` (or `%LOCALAPPDATA%/vessel` on Windows).
- **Per-vessel isolation** — each vessel has its own `Droplets/`, `Materials/`, `AI/` directories and `.vessel/` metadata folder containing the RAG database, chat history, and calendar events.

### Droplets (Markdown Notes)
- **Live Markdown editor** with split-pane **render mode** — write in Markdown, preview formatted output side-by-side.
- **File tree browser** — navigate your droplet directory structure with folder nesting, create new files/folders, rename, and delete.
- **Auto-save** — unsaved changes are persisted to disk on window close via a guaranteed shutdown handler.
- **Multi-format** — supports `.md`, `.html`, and `.txt` files within the Droplets directory.
- **Welcome note** — auto-created when you create a new vessel.

### Materials (File Vault)
- **Drag-and-drop file upload** — copy files into the vessel's `Materials/` directory with a single click. Files are automatically indexed for search.
- **Broad format support:**
  - **Documents:** PDF, DOC, DOCX, PPT, PPTX, HTML, TXT, CSV, JSON
  - **Images:** PNG, JPG, JPEG, GIF, BMP, WebP, SVG
  - **Video:** MP4, AVI, MOV, MKV, WebM
- **Content preview** — inline viewing for PDFs (via Qt's PDF engine), HTML, Markdown, TXT, CSV, and JSON. Other file types open with your system's default application.
- **Automatic text extraction** — uploaded files go through a LangGraph ingestion pipeline that extracts text, generates tags, and creates vector embeddings.

### Upload & Ingestion Pipeline
When a file is uploaded to Materials, a **LangGraph pipeline** processes it automatically:

1. **Format conversion** — PPT/DOC files are converted to PDF via LibreOffice.
2. **Text extraction:**
   - **PDF** — extracted via `pdftotext` (poppler-utils) with PyMuPDF fallback.
   - **HTML** — tag stripping via Python's stdlib `HTMLParser`.
   - **Images** — OCR via Tesseract.
   - **Video** — single-frame grab via ffmpeg + Tesseract OCR.
3. **Tag generation** — 10-strategy aggressive tag extraction (file identity, file-name parts, word frequency, title-case phrases, ALL-CAPS acronyms, CamelCase identifiers, numbers, hyphenated compounds, TF signal boosting, short-jargon boost). Up to 30 tags per document.
4. **Vector embedding** — 768-dimensional embeddings via Ollama (`nomic-embed-text`) with sentence-transformers (`all-MiniLM-L6-v2`) fallback, stored in sqlite-vec.
5. **Text persistence** — extracted text is saved as `.txt` in the vessel's `AI/content/` directory.
6. **FTS5 auto-sync** — full-text search index is automatically kept in sync via SQLite triggers.

### AI Chat & RAG Query Engine
- **Conversational RAG** — ask questions about your notes and materials, get answers grounded in your own data.
- **Multi-channel retrieval** — queries are processed through a **LangGraph state machine** that runs retrievers in parallel:
  - **Vector search** — semantic similarity via sqlite-vec (cosine distance).
  - **BM25 keyword search** — SQLite FTS5 with ranked results.
  - **Tag search** — inverted-index lookup via junction tables.
  - **Web search** — optional DuckDuckGo integration for online augmentation.
- **Query classification** — automatically detects whether a query is a **question** (answer from context) or a **summarize/generate request** (produce study material, flashcards, key points). For "all documents" requests, every document is fetched; for specific topics, tag + vector search on the topic keyword is used.
- **Code generation** — queries requiring calculation or data processing trigger a code generation node that produces and executes Python scripts (stdlib only) in a sandboxed subprocess.
- **Answer refinement loop** — generated answers are scored on completeness, accuracy, and clarity (0–10). Low-scoring answers are automatically refined up to 3 times with specific feedback.
- **Chat history** — per-vessel persistent conversations stored as JSON files in `.vessel/chats/`. Conversations are auto-titled from the first user message.
- **Multi-turn context** — conversational context is threaded through the pipeline for follow-up questions.

### Multi-Provider AI Support
- **Ollama** (default) — local LLMs running on your machine. Configurable model name.
- **OpenAI** — GPT models via API key.
- **Anthropic** — Claude models via API key.
- **Google** — Gemini models via API key.
- **Seamless switching** — change providers in the settings at any time. All providers share the same RAG pipeline.
- **Embeddings** — Ollama (`nomic-embed-text`) for local setups; sentence-transformers fallback for non-Ollama providers.

### Tag System
- **Automatic tagging** — when files are ingested, the upload pipeline extracts tags using 10 strategies:
  1. File type classification
  2. File extension tags
  3. File-name word segmentation
  4. Lowercase word frequency
  5. Title-case terms (proper nouns)
  6. Multi-word title-case phrases
  7. ALL-CAPS acronyms
  8. CamelCase identifiers
  9. Numeric values
  10. Hyphenated compounds
- **Inverted-index search** — junction table (`document_tags`) linking documents to tags enables fast tag-based retrieval.
- **False-positive tolerant** — designed to over-generate tags; recall is preferred over precision for RAG retrieval.

### Calendar
- **Per-vessel event tracking** — lightweight JSON-based calendar stored in `.vessel/events.json`.
- **Create and delete events** — each event has a title, date, and auto-generated ID.
- **Upcoming events panel** — sorted list of events from today onward.

### PDF Viewer
- **Built-in PDF rendering** — uses Qt's PDF engine (`QtQuick.Pdf`) for native in-app viewing.

### Customizable Themes
- **Full color customization** — 8 configurable color properties: background (dark, card, panel), border, text (primary, secondary), accent, and danger.
- **Persistent theme config** — saved to `~/.config/vessel/theme_config.json`.
- **Real-time updates** — theme changes apply immediately to the UI via Qt property bindings.

### Local-First & Privacy
- **100% offline capable** — everything runs on your machine. No cloud dependency, no data leaves your computer unless you enable web search.
- **No telemetry, no accounts, no sign-ups.**
- **Your data, your files** — vessels are standard directories on your filesystem. Documents are stored as plain text files in `AI/content/`. The RAG database is a standard SQLite file.

---

## Installing

### Pre-built Binaries

Pre-built binaries are available on the [Releases](https://github.com/iamsurjog/Vessel/releases) page. Download the archive for your platform, extract it, and run the executable.

### Build from Source

**Prerequisites:** Python 3.14.5 (nearby versions 3.12–3.13 may work but are untested). Optional dependencies for full file format support: LibreOffice, poppler-utils, Tesseract OCR, ffmpeg.

```bash
# Clone the repo
git clone https://github.com/iamsurjog/Vessel.git
cd Vessel

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

> **Note:** Development targets Python 3.14.5. Nearby versions (3.12, 3.13) may work, but have not been tested.

---

## Usage

### Vessels
- **Launch** the application — you'll see the **Launcher** screen.
- **Create a new vessel** — enter a name and choose a parent directory. A new vessel directory is created with `Droplets/`, `Materials/`, `AI/`, and `.vessel/` subdirectories.
- **Open an existing vessel** — select from the vessel registry or open any vessel directory.
- **Delete a vessel** — removes the vessel from the registry and optionally deletes the directory.

### Droplets
- Navigate the **file tree** in the sidebar to browse your Markdown notes.
- **Click** a file to open it in the editor. The editor supports live Markdown rendering.
- **Right-click** (or use the toolbar) to create new files/folders, rename, or delete.
- Files are saved automatically when you close the workspace.

### Materials
- **Click "Upload"** to copy a file from your system into the current vessel's Materials directory.
- Files are automatically processed (text extraction, tagging, vector embedding — see the Upload Pipeline above).
- **Click** a file to preview it. PDFs open in the built-in PDF viewer; HTML/Markdown/TXT/CSV/JSON show their text content; other files open with your system default.

### AI Chat
- Open a vessel, then navigate to the **Chat** panel.
- **Ask questions** about your notes and materials — the AI searches your documents and returns grounded answers.
- **Toggle web search** to also include DuckDuckGo results in the response.
- **Conversation history** is preserved per vessel. Start a new conversation or pick up where you left off.

### Calendar
- **Add events** with a title and date.
- **View upcoming events** — events from today onward are shown in a sorted panel.
- **Delete events** as needed.

---

## Architecture

### Upload Pipeline

```
File Upload
    |
    v
[filetype_router] ──▶ PPT/DOC ──▶ [convert_to_pdf] (LibreOffice)
    |                                      |
    |                                     PDF
    |                                      |
    ├──▶ PDF/TXT/HTML ──▶ [extract_text] ──┤
    |                      (pdftotext /     |
    |                       HTMLParser /    |
    |                       direct read)    |
    |                                      │
    └──▶ Image/Video ──▶ [generate_description]
                          (Tesseract OCR /   |
                           ffmpeg+OCR)       |
                                             v
                        ┌────────────────────┐
                        │  Parallel Storage   │
                        │  ┌──────────────┐  │
                        │  │ Vector Embed │  │  sqlite-vec (768d)
                        │  ├──────────────┤  │
                        │  │ Store as TXT │  │  AI/content/*.txt
                        │  ├──────────────┤  │
                        │  │ Tags (×30)  │  │  tags + document_tags
                        │  └──────────────┘  │
                        └────────────────────┘
```

### Query Pipeline

```
User Query
    |
    v
[classify_node] ──▶ answer_q ──▶ [parallel search]
    |                   |           ├── vector_search (sqlite-vec)
    |                   |           ├── keyword_search (FTS5 BM25)
    |                   |           └── web_search (DuckDuckGo, optional)
    |                   |
    |                   ├── [generate_py_script] (if calculation needed)
    |                   |
    |                   └── [generate_answer] ──▶ [quality_check]
    |                                                  |
    |                                           (score < 7?) ──▶ [refine_answer] ──loop
    |                                                  |
    |                                              (score ≥ 7) ──▶ END
    |
    └──▶ summarize ──▶ [parse_summarize_query]
                           |
                    ┌──────┴──────┐
                    v              v
            [get_all_docs]   [search_by_topic]
                                 (tag + vector)
                    |              |
                    └──────┬──────┘
                           v
                    [check_if_relevant]
                           |
                     (relevant?) ──▶ [generate_answer] → [quality_check] → END
                           |
                     (irrelevant) ──▶ END
```

### Database Schema

Each vessel has a `.vessel/vessel_rag.db` SQLite database:

- **`documents`** — primary document store: `id`, `title`, `text_chunk`
- **`tags`** — unique tag names: `id`, `name`
- **`document_tags`** — many-to-many junction: `doc_id`, `tag_id`
- **`v_document_embeddings`** — sqlite-vec virtual table, 768-dimensional float vectors
- **`documents_fts`** — FTS5 virtual table for BM25 full-text search (auto-synced via triggers)

---

## AI Providers

| Provider   | Default Model          | Requires    | Embeddings          |
|------------|------------------------|-------------|---------------------|
| Ollama     | `tinyllama:1.1b`       | Ollama server running locally | nomic-embed-text (local) |
| OpenAI     | `gpt-4o-mini`          | API key     | sentence-transformers |
| Anthropic  | `claude-3-haiku-20240307` | API key  | sentence-transformers |
| Google     | `gemini-2.0-flash`     | API key     | sentence-transformers |

Configure providers in **Settings** → **AI Provider**.

---

## Configuration

Configuration files are stored at:
- **Linux:** `~/.config/vessel/`
- **macOS:** `~/.config/vessel/`
- **Windows:** `%LOCALAPPDATA%/vessel/`

| File | Purpose |
|------|---------|
| `vessels_history.json` | Vessel registry (list of known vessels) |
| `provider_config.json` | AI provider settings (provider, model, API keys) |
| `theme_config.json` | UI theme colors |

### Environment Variables

| Variable | Value | Effect |
|----------|-------|--------|
| `VESSEL_LOG_LEVEL` | `0` (default) | Quiet — no extra output |
| `VESSEL_LOG_LEVEL` | `1` | General — API errors, status codes, missing keys |
| `VESSEL_LOG_LEVEL` | `2` | Highly specific — request/response bodies, pipeline timing |

Set it before running:

```bash
VESSEL_LOG_LEVEL=2 python main.py
```

---



## Tech Stack

- **UI Framework:** PySide6 (Qt 6.11) + QML (QtQuick Controls)
- **AI Pipeline:** LangGraph (1.2.x) — state machine orchestration
- **Vector Search:** sqlite-vec (0.1.x) — 768-dim embeddings
- **Full-Text Search:** SQLite FTS5 with BM25 ranking
- **Embedding Models:** nomic-embed-text (Ollama) / all-MiniLM-L6-v2 (sentence-transformers)
- **LLM Providers:** Ollama, OpenAI, Anthropic, Google Gemini
- **Web Search:** DuckDuckGo (ddgs/duckduckgo_search)
- **Document Processing:** pdftotext, LibreOffice, Tesseract OCR, ffmpeg
- **Python:** 3.14+

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

---

## License

This project is licensed under the terms included in the repository.
