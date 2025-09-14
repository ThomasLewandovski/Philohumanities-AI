from __future__ import annotations

import json
import time
from typing import AsyncGenerator, Dict

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from ..config import get_settings
from ..generation import OpenAICompatProvider
from ..llm_client import LLMClient
from ..role_cards import RoleCardRegistry
from ..schemas import Message
from ..storage import Storage


router = APIRouter(prefix="/api", tags=["role-chat"])


def _storage() -> Storage:
    s = get_settings()
    return Storage(s.data_dir)


def _registry() -> RoleCardRegistry:
    return RoleCardRegistry()


def _provider() -> OpenAICompatProvider:
    s = get_settings()
    client = LLMClient(base_url=s.llm_base_url, api_key=s.llm_api_key, default_model=s.llm_model)
    return OpenAICompatProvider(client)


@router.post("/role-conversations")
def create_role_conversation(payload: Dict[str, object]):
    slug = payload.get("roleCardId") or payload.get("slug")
    title = payload.get("title") or None
    if not slug or not isinstance(slug, str):
        raise HTTPException(status_code=400, detail="roleCardId is required")
    rc = _registry().get(slug)
    if not rc:
        raise HTTPException(status_code=404, detail="role card not found")
    # Use the persona prompt as system message
    system = rc.system_prompt
    if rc.style_hints:
        system = f"{system}\n风格：{rc.style_hints}"
    st = _storage()
    meta = st.create_conversation(title or f"与{rc.name}的对话", system)
    return {
        "conversationId": meta.id,
        "title": meta.title,
        "roleCardId": rc.slug,
        "roleCardName": rc.name,
        "createdAt": meta.createdAt,
    }


async def _sse(role_slug: str, cid: str, text: str, temperature: float = 0.7, max_tokens: int = 300) -> AsyncGenerator[bytes, None]:
    reg = _registry()
    rc = reg.get(role_slug)
    if not rc:
        yield _sse_event("error", {"code": "role_not_found", "message": "role card not found"})
        return

    st = _storage()
    try:
        st.get_messages(cid)
    except FileNotFoundError:
        yield _sse_event("error", {"code": "not_found", "message": "conversation not found"})
        return

    # append user message first
    user_msg = Message(role="user", content=text)
    st.append_message(cid, user_msg)

    provider = _provider()
    # build minimal history
    history = [{"role": m.role, "content": m.content} for m in st.get_messages(cid)]

    # Create an assistant message shell id using timestamp surrogate
    message_id = f"asst-{int(time.time()*1000)}"
    yield _sse_event("status.start", {"conversationId": cid, "roleCardId": rc.slug, "model": "openai-compatible", "promptVersion": 1})
    yield _sse_event("message.created", {"messageId": message_id, "state": "generating"})

    collected = []
    async for delta in provider.stream_reply(rc, history, temperature=temperature, max_tokens=max_tokens):
        collected.append(delta)
        yield _sse_event("message.delta", {"messageId": message_id, "delta": delta})

    final_text = "".join(collected)
    asst_msg = Message(role="assistant", content=final_text)
    st.append_message(cid, asst_msg)
    yield _sse_event("message.completed", {"messageId": message_id, "usage": {"promptTokens": 0, "completionTokens": len(final_text) // 4}, "finishReason": "stop"})
    yield b"event: done\n\n"


def _sse_event(event: str, data: Dict[str, Any]) -> bytes:
    return f"event: {event}\n".encode() + f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@router.post("/role-conversations/{cid}/assistant/stream")
async def role_assistant_stream(cid: str, payload: Dict[str, object]):
    text = payload.get("text")
    role = payload.get("roleCardId") or payload.get("slug")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    if not isinstance(role, str):
        raise HTTPException(status_code=400, detail="roleCardId is required")
    temperature = float(payload.get("temperature") or 0.7)
    max_tokens = int(payload.get("max_tokens") or 300)
    generator = _sse(role, cid, text, temperature=temperature, max_tokens=max_tokens)
    return StreamingResponse(generator, media_type="text/event-stream")
