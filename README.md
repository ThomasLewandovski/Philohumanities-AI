# Philohumanities-AI

Philohumanities-AI (Local Chat App scaffold)

Overview
- Backend: Python FastAPI, proxies to an OpenAI-compatible LLM endpoint (e.g., vLLM/Ollama gateway/OpenAI-compatible service). No DB.
- Frontend: Simple static HTML + JS served by FastAPI.
- Storage: Chat history persists to local files under `data/` (per repository).

Key Features
- Local file history: persists under project `data/`, shared across browsers on same host.
- Simple chat UI: create/delete conversations, send messages, basic export of current convo.
- Pluggable LLM provider: configure base URL, API key, and model via environment variables.

Limitations
- No multi-user accounts; single-process file storage recommended.
- Import/export minimal on front-end (current conversation only).

Getting Started
1) Create a virtualenv and install dependencies:
   `python -m venv .venv`
   `source .venv/bin/activate`  (Windows: `.venv\\Scripts\\activate`)
   `pip install -r requirements.txt`

2) Configure environment variables (examples):
   `cp .env.example .env` then edit values, or export directly:
   `export LLM_BASE_URL="http://localhost:8001"`    # Your OpenAI-compatible endpoint base (no trailing slash)
   `export LLM_API_KEY="sk-..."`                     # If required; leave unset if not
   `export LLM_MODEL="qwen2"`                        # Model name exposed by your provider
   `export DATA_DIR="./data"`

3) Run the server:
   `uvicorn backend.main:app --reload --port 3000`

4) Open the app:
   `http://localhost:3000`

Folder Structure
- `backend/main.py`: FastAPI app, API routes, static hosting
- `backend/config.py`: Env settings loader
- `backend/schemas.py`: Pydantic models
- `backend/storage.py`: File-based storage under `data/`
- `backend/routes/`: Conversations + chat endpoints
- `backend/llm_client.py`: LLM calling helper (OpenAI-compatible, non-streaming for now)
- `static/index.html`: Chat UI page
- `static/app.js`: Frontend logic (uses REST API; storage on server files)
- `static/styles.css`: Minimal styles
- `docs/API_SPEC.md`: API contract
- `requirements.txt`: Python dependencies

Next Steps (optional)
- Add streaming responses (SSE or fetch streaming) to show token-by-token output.
- Switch localStorage to IndexedDB for very long histories.
- Add RAG, prompt templates, or model switcher UI.
- A few bugs tobe fixed.
- UI
