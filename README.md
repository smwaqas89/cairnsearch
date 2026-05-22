# 🔍 cairnsearch

<div align="center">

**A privacy-first, AI-powered local document search engine**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[Features](#features) • [Installation](#installation) • [Quick Start](#quick-start) • [Documentation](#documentation) • [Contributing](#contributing)

</div>

---

## 📄 Paper

This software is described in a paper submitted to *SoftwareX*:

> Waqas, M. (2026). *cairnsearch: A privacy-first hybrid search and local RAG system for personal document collections.* Submitted.

If you use cairnsearch in your work, please cite using the `CITATION.cff` metadata in this repository, or via the "Cite this repository" button in the GitHub sidebar.

---

## ✨ Features

### 🔎 Powerful Search
- **Full-text search** with BM25 ranking
- **Boolean queries**: `contract AND texas NOT amendment`
- **Phrase search**: `"exact phrase match"`
- **Field search**: `filename:report type:pdf author:john`
- **Date filters**: `after:2023-01-01 before:2024-01-01`

### 🤖 AI-Powered Q&A (RAG)
- **Ask questions** about your documents in natural language
- **Get cited answers** with source document references
- **100% local AI** with Ollama - no data leaves your machine
- **Hybrid search** combining keyword + semantic search

### 📁 Wide File Support
| Documents | Spreadsheets | Images | Other |
|-----------|--------------|--------|-------|
| PDF | XLSX | PNG (OCR) | HTML |
| DOCX | XLS | JPG (OCR) | JSON |
| DOC | CSV | TIFF (OCR) | XML |
| TXT/MD | TSV | | |

### 🔒 Privacy First
- **100% Local** - Everything runs on your machine
- **No cloud required** - Works completely offline
- **No telemetry** - Your data stays yours
- **Open source** - Audit the code yourself

---

## 🚀 Installation

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) (for AI features)
- Tesseract OCR (optional, for scanned documents)

### One-click install (easiest)

For a non-developer setup, the bundled installer creates a virtual
environment, installs cairnsearch, and pulls the default Ollama models:

```bash
# macOS / Linux
git clone https://github.com/smwaqas89/cairnsearch.git
cd cairnsearch
./install.sh
```

```bat
REM Windows
git clone https://github.com/smwaqas89/cairnsearch.git
cd cairnsearch
install.bat
```

The script prints the exact command to start the server when it finishes.

### Quick Install (manual)

```bash
# Clone the repository
git clone https://github.com/smwaqas89/cairnsearch.git
cd cairnsearch

# Install
pip install -e .

# Initialize
cairnsearch init

# Start the web UI
./run.sh serve
```

Open http://localhost:8080 in your browser.

### Install with AI Features

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Download required models
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# Install cairnsearch with RAG support
pip install -e ".[rag]"
```

### macOS Additional Setup

```bash
# Install Tesseract for OCR support
brew install tesseract

# If using port 5000 conflicts with AirPlay
# The app runs on port 8080 by default
```

### Windows Installation

See [WINDOWS_INSTALL.md](WINDOWS_INSTALL.md) for detailed Windows setup instructions.

---

## 📖 Quick Start

### 1. Add Folders to Index

Open http://localhost:8080, go to **Settings**, and add folders you want to search.

Or via CLI:
```bash
cairnsearch reindex ~/Documents ~/Projects
```

### 2. Search Your Documents

Type your query and press Enter:
- `contract payment terms` - keyword search
- `"state of texas"` - exact phrase
- `type:pdf after:2023-01-01` - with filters

### 3. Ask AI Questions

Click **Ask AI** and type a natural language question:
- "What are the payment terms in our vendor contracts?"
- "Summarize the key points from the Q3 report"
- "Find documents mentioning Project Alpha"

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `/` | Focus search |
| `Enter` | Search |
| `⇧ Enter` | Ask AI |
| `⌘/Ctrl + K` | Command palette |
| `Esc` | Close panel |

---

## 🛠️ CLI Commands

```bash
# Search
cairnsearch search "contract texas"
cairnsearch ask "What are the payment terms?"

# Indexing
cairnsearch reindex              # Reindex all folders
cairnsearch reindex ~/Documents  # Index specific folder

# Server
cairnsearch serve                # Start web server (port 8080)
cairnsearch watch                # Watch folders for changes

# Status
cairnsearch status               # Show index statistics
cairnsearch rag-status           # Show AI system status
```

---

## 📡 API

cairnsearch provides a REST API for integration:

```bash
# Search
curl "http://localhost:8080/api/search?q=contract"

# Ask AI
curl -X POST http://localhost:8080/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the payment terms?"}'

# Status
curl http://localhost:8080/api/status
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/search?q=...` | Search documents |
| GET | `/api/suggest?q=...` | Get search suggestions |
| GET | `/api/status` | Index statistics |
| GET | `/api/documents/{id}` | Get document details |
| POST | `/api/documents/{id}/open` | Open document in system |
| POST | `/api/rag/ask` | Ask AI a question |
| POST | `/api/index/start` | Start indexing |
| DELETE | `/api/index` | Clear index |

---

## ⚙️ Configuration

Create `~/.config/cairnsearch/config.toml`:

```toml
[general]
data_dir = "~/.local/share/cairnsearch"

[watcher]
folders = ["~/Documents", "~/Projects"]
ignore_patterns = ["*.tmp", ".git", "__pycache__"]

[indexer]
workers = 4
max_file_size_mb = 500

[rag]
llm_provider = "ollama"
ollama_model = "llama3.2"
embedding_model = "nomic-embed-text"
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Web UI                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Server                          │
├─────────────────────┬─────────────────┬─────────────────────┤
│    Search API       │    RAG API      │    Index API        │
└─────────────────────┴─────────────────┴─────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  SQLite FTS5    │  │  Vector Store   │  │   Job Queue     │
│  (BM25 Search)  │  │  (Embeddings)   │  │   (Indexing)    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │     Ollama      │
                     │  (Local LLM)    │
                     └─────────────────┘
```

---

## 🔒 Privacy & Architecture Notes

### Local-only by default

cairnsearch makes **no external network calls** by default. The `strict_local`
setting (in `[rag]`, default `true`) enforces this: cloud providers (OpenAI,
Anthropic) are refused before any request is sent — in the LLM factory, the
embedder factory, and the connection-test and config API endpoints. Document
content, queries, and embeddings stay on your machine.

To opt in to a cloud provider (your data would then be sent to it), set
`strict_local = false` in your config and supply the relevant API key via an
environment variable.

### Reranking

Reranking is **disabled by default** for speed. When enabled, the default
reranker is a **local LLM-based (listwise) reranker**: it asks the local Ollama
model to score each candidate chunk's relevance, keeping the rerank step fully
local with no extra model download. This differs from a classical
*cross-encoder* reranker; a true cross-encoder
(e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`) can be plugged in by implementing
`BaseReranker` in `src/cairnsearch/rag/reranker.py`.

### Chunking

The default chunk size is **500 tokens with 50-token overlap**. This balances
retrieval granularity (small enough that a retrieved chunk is mostly relevant
to the query) against context coherence (large enough to keep a clause or
paragraph intact). Tables are chunked on row boundaries only, never mid-row.
Both values are configurable under `[rag]`. See [docs/SCHEMA.md](docs/SCHEMA.md)
for the full chunk schema and the OCR-bounding-box → index mapping.

### PII detection

The PII detector flags twelve classes of sensitive data (SSN, credit card,
email, phone, address, date of birth, passport, driver's licence, bank account,
IP, name, medical record) using regular expressions and lightweight heuristics.
It is intentionally a **recall-oriented safety net** for flagging and redaction
review — not a high-precision classifier. Expect false positives (e.g. numbers
that look like account numbers) and some false negatives on unusual formats. It
should not be relied on as the sole control for regulatory compliance.

### Resource handling

If the local LLM runs out of memory or cannot be reached, cairnsearch returns a
clear, actionable error (for example, suggesting a smaller model such as
`llama3.2:1b`) rather than crashing silently.

### Extractor sandboxing

External extractors (OCR, archive handling) run in isolated subprocesses with
POSIX resource limits (memory, CPU time, no core dumps) and a stripped
environment that withholds API keys. This contains the impact of a malformed or
malicious document.

---

## 📊 Query Syntax

| Syntax | Example | Description |
|--------|---------|-------------|
| Keywords | `contract texas` | Both words required |
| Phrases | `"state of texas"` | Exact phrase |
| AND | `contract AND texas` | Both terms required |
| OR | `contract OR agreement` | Either term |
| NOT | `contract NOT amendment` | Exclude term |
| filename | `filename:report` | Search filename |
| type | `type:pdf` | Filter by type |
| author | `author:smith` | Filter by author |
| after | `after:2022-01-01` | Date filter |
| before | `before:2023-12-31` | Date filter |

**Example**: `filename:contract "state of texas" type:pdf after:2022-01-01`

---

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/smwaqas89/cairnsearch.git
cd cairnsearch
pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format src/
```

---

## 🐛 Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

**Common Issues:**
- Port 5000 conflict on macOS → Use port 8080 (default)
- Ollama not running → Start with `ollama serve`
- OCR not working → Install Tesseract: `brew install tesseract`

---

## 📜 License

[MIT License](LICENSE) © 2026 Muhammad Waqas

---

## 🙏 Acknowledgments

- [SQLite FTS5](https://www.sqlite.org/fts5.html) for full-text search
- [Ollama](https://ollama.com/) for local LLM inference
- [FastAPI](https://fastapi.tiangolo.com/) for the API server
- [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF extraction

---

<div align="center">

**[⬆ Back to Top](#-cairnsearch)**

Made with ❤️ for privacy

</div>
