import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from .config import get_settings
from .llm_client import LLMClient
from .routes.conversations import router as conversations_router
from .routes.chat import router as chat_router
from .routes.roles import router as roles_router
from .routes.role_chat import router as role_chat_router
from .routes.providers import router as providers_router
from .routes.group_chat import router as group_chat_router
from .routes.kb import router as kb_router
from .routes.suggestions import router as suggestions_router


app = FastAPI(title="Philohumanities-AI (local)")

# CORS: if serving static from same origin, not strictly needed; safe default
try:
    settings = get_settings()
except Exception:
    # Defer settings validation for /health to work even if unset
    settings = None  # type: ignore

allow_origins = ["*"] if settings is None else settings.allow_origins
app.add_middleware(CORSMiddleware, allow_origins=allow_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


def _get_llm_client() -> LLMClient:
    try:
        s = get_settings()
        return LLMClient(base_url=s.llm_base_url, api_key=s.llm_api_key, default_model=s.llm_model)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(roles_router)
app.include_router(role_chat_router)
app.include_router(providers_router)
app.include_router(group_chat_router)
app.include_router(kb_router)
app.include_router(suggestions_router)


# Serve static frontend (index.html at root)
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
static_dir = os.path.abspath(static_dir)
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

__all__ = ["app"]
