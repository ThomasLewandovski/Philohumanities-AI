from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from ..knowledge_base import KnowledgeBaseManager


router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


def _kb() -> KnowledgeBaseManager:
    return KnowledgeBaseManager()


@router.post("")
def create_kb(payload: Dict[str, Any]):
    title = payload.get("title") or "未命名知识库"
    role = payload.get("roleCardId")
    meta = _kb().create_kb(str(title), str(role) if isinstance(role, str) else None)
    return meta


@router.get("")
def list_kb():
    return _kb().list_kb()


@router.get("/role/{slug}")
def list_role_kb(slug: str):
    return _kb().list_role_kb(slug)


@router.post("/{kbId}/ingest-text")
def ingest_text(kbId: str, payload: Dict[str, Any]):
    title = payload.get("title") or "未命名文档"
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    try:
        doc = _kb().ingest_text(kbId, str(title), text)
        return doc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="kb not found")


@router.get("/{kbId}/docs")
def list_docs(kbId: str):
    return _kb().list_docs(kbId)

