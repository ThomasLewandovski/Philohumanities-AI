from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..app.dependencies import get_llm_client, get_storage
from ..core.conversations.models import Message, SendMessageReq, SendMessageResp


router = APIRouter(prefix="/api/conversations", tags=["chat"])


@router.post("/{cid}/messages", response_model=SendMessageResp)
async def send_message(cid: str, req: SendMessageReq):
    st = get_storage()
    try:
        # Ensure conversation exists
        st.get_messages(cid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")

    # Append user message
    user_msg = Message(role="user", content=req.content)
    st.append_message(cid, user_msg)

    # Build history for LLM: include all messages
    history = st.get_messages(cid)
    messages: List[Dict[str, Any]] = [
        {"role": m.role, "content": m.content} for m in history
    ]

    # Call LLM
    client = get_llm_client()
    try:
        result = await client.chat_completion(
            messages=messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=False,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    content = ""
    try:
        content = result["choices"][0]["message"]["content"] or ""
    except Exception:
        content = ""

    assistant_msg = Message(role="assistant", content=content)
    st.append_message(cid, assistant_msg)
    return SendMessageResp(assistant=assistant_msg)
