# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A C++ multi-repository code dependency analysis and visualization system. Parses C++ source via Tree-sitter, stores symbols and dependencies in SQLite, and renders dependency graphs via D3.js. Designed for analyzing Visual Studio `.sln`/`.vcxproj` based projects.

## Commands

### Backend (Python)

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run server (http://localhost:8000)
cd backend
python main.py

# Alternative: run via uvicorn directly
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000

# Windows one-click start/stop
start.bat   # creates .venv, installs deps, launches uvicorn
stop.bat    # kills python processes
```

There is no test suite. The `test_*.py` and `debug_*.py` files at the repo root are ad-hoc scripts, not a test framework.

### Frontend (React + Vite + D3)

```bash
cd frontend
pnpm install
pnpm dev        # dev server on http://localhost:3000, proxies /api to :8000
pnpm build      # outputs to frontend/dist/
```

The frontend dev server proxies `/api` requests to the backend at `localhost:8000`. The production frontend is pre-built into `static/` and served by FastAPI as static files.

## Architecture

### Backend (`backend/`)

All backend modules import each other by bare name (no package prefix) — they run with CWD set to `backend/`.

- **`main.py`** — FastAPI app with all REST endpoints. Defines Pydantic request/response models inline. Initializes `Database` and `MultiLayerCodeParser` at module level.
- **`database.py`** — `Database` class wrapping SQLite. Tables: `repositories`, `symbols`, `dependencies`, `layers`. Uses per-request connections with context manager. Default DB path: `data/dependency.db`.
- **`models.py`** — Dataclasses: `Repository`, `Symbol`, `Dependency`, `GraphNode/Edge/Data`, `SearchQuery/Result`, `CallbackInfo`. Enums: `SymbolKind`, `DependencyType`. `DEFAULT_LAYERS` defines the 4 built-in layers (SDK, LOGIC, BUSINESS, UI).
- **`parser.py`** — `VSProjectResolver` (parses `.sln`/`.vcxproj` to find source files) and `MultiLayerCodeParser` (Tree-sitter based C++ parser). Falls back to regex parsing if Tree-sitter is unavailable. Extracts symbols, `#include` deps, and function call deps.
- **`enhanced_call_extractor.py`** — `EnhancedCallExtractor` walks Tree-sitter ASTs to extract function calls, lambda callbacks, and constructor initializations. Tracks namespace/class context for qualified names.

### Frontend

Two frontends exist:

1. **`static/index.html`** — The original single-file frontend (HTML + D3.js, no build step). Currently deployed and served by FastAPI.
2. **`frontend/`** — A newer React + TypeScript + Vite app with components (`ClassTreePanel`, `CallTreeView`, `RepoPanel`, `GraphView`, `NodeDetail`, `SearchPanel`). This is the active development frontend.

### Data Flow

1. User registers a repository (path + layer) via API
2. User triggers parse (recursive scan or VS solution parse)
3. `MultiLayerCodeParser` reads `.sln` → `.vcxproj` → source files, builds Tree-sitter ASTs
4. Symbols and raw dependency dicts are stored in SQLite; function calls are matched to symbol IDs by name
5. Frontend fetches graph data from `/api/graph` or symbol-specific graphs from `/api/graph/symbol/{id}`
6. D3.js renders force-directed graphs

### Key API patterns

All responses use `ApiResponse(success, message, data)` envelope. Two parse modes: `/api/repositories/{id}/parse` (recursive directory scan) and `/api/repositories/{id}/parse-vs` (VS solution aware). Call-tree endpoints (`/api/symbols/{id}/call-tree*`) return tree-structured data with recursion detection.

## Key Technical Details

- **Symbol matching**: Dependencies are matched to symbols by function name (with fallback to base name stripping `::` qualifiers). This is imprecise — multiple overloads or同名 functions may match incorrectly.
- **Hashing**: Symbols get SHA-256 hashes (truncated to 16 chars) of their signature, used for deduplication via `INSERT OR IGNORE`.
- **Virtual symbols**: `#include` targets that aren't resolved to existing symbols get "virtual" symbols with `kind='include'` created automatically.
- **Database location**: `data/dependency.db` relative to repo root (configured in `main.py` and `database.py` as `Path(__file__).parent.parent / "data"`).
- **Logs**: Written to `logs/app.log` via Python logging.
