import json

from fastapi import APIRouter, HTTPException, Request

from ..app.dependencies import get_storage
from ..core.conversations.models import ConversationMeta, CreateConversationReq, Message
from ..infrastructure.paths import prompts_dir


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationMeta])
def list_conversations():
    return get_storage().list_conversations()



@router.post("", response_model=ConversationMeta)
async def create_conversation(req: CreateConversationReq, request: Request):
    # 支持角色卡机制
    data = await request.json()
    role = data.get("role")
    title = data.get("title")
    system = req.system
    greeting = None
    if role:
        prompt_path = prompts_dir() / f"{role}.json"
        if prompt_path.exists():
            with prompt_path.open("r", encoding="utf-8") as f:
                prompt_data = json.load(f)
            # prompt 只作为system prompt
            system = prompt_data.get("prompt") or prompt_data.get("content") or str(prompt_data)
            greeting = prompt_data.get("greeting")
    storage = get_storage()
    meta = storage.create_conversation(req.title, system)
    # 创建后将greeting作为assistant消息加入
    if greeting:
        storage.append_message(meta.id, Message(role="assistant", content=greeting))
    return meta


@router.patch("/{cid}", response_model=ConversationMeta)
def rename_conversation(cid: str, payload: dict):
    title = payload.get("title")
    if not title or not isinstance(title, str):
        raise HTTPException(status_code=400, detail="title is required")
    try:
        return get_storage().rename_conversation(cid, title)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")


@router.delete("/{cid}", status_code=204)
def delete_conversation(cid: str):
    try:
        get_storage().delete_conversation(cid)
        return None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")


@router.get("/{cid}/messages")
def get_messages(cid: str):
    try:
        msgs = get_storage().get_messages(cid)
        return {"id": cid, "messages": msgs}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")
