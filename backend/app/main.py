from pathlib import Path
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .dependencies import get_settings
from ..api.conversations import router as conversations_router
from ..api.chat import router as chat_router
from ..api.roles import router as roles_router
from ..api.role_chat import router as role_chat_router
from ..api.providers import router as providers_router
from ..api.group_chat import router as group_chat_router
from ..api.kb import router as kb_router
from ..api.suggestions import router as suggestions_router


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
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(roles_router)
app.include_router(role_chat_router)
app.include_router(providers_router)
app.include_router(group_chat_router)
app.include_router(kb_router)
app.include_router(suggestions_router)


# Serve static frontend (index.html at project root / static)
static_dir = Path(__file__).resolve().parents[2] / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

__all__ = ["app"]
