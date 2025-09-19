from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..app.dependencies import get_storage
from ..core.suggestions.generator import generate_suggestions


router = APIRouter(prefix="/api", tags=["suggestions"])


def _ensure_conv(cid: str) -> None:
    st = get_storage()
    try:
        st.get_messages(cid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")


@router.post("/conversations/{cid}/suggestions")
async def suggest(cid: str, payload: Dict[str, Any]):
    _ensure_conv(cid)
    k = int(payload.get("k") or 4)
    max_sentences = int(payload.get("maxSentences") or 2)
    angles = payload.get("angles") if isinstance(payload.get("angles"), list) else None
    locale = payload.get("locale") if isinstance(payload.get("locale"), str) else None
    diversify = bool(payload.get("diversify") or False)
    data = await generate_suggestions(cid, k=k, max_sentences=max_sentences, angles=angles, locale=locale, diversify=diversify)
    return data
