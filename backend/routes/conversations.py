from fastapi import APIRouter, HTTPException,Request

from ..config import get_settings
from ..schemas import ConversationMeta, CreateConversationReq
from ..storage import Storage
import os, json


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _storage() -> Storage:
    s = get_settings()
    return Storage(s.data_dir)


@router.get("", response_model=list[ConversationMeta])
def list_conversations():
    return _storage().list_conversations()



@router.post("", response_model=ConversationMeta)
async def create_conversation(req: CreateConversationReq, request: Request):
    # 支持角色卡机制
    data = await request.json()
    role = data.get("role")
    title = data.get("title")
    system = req.system
    greeting = None
    if role:
        # 兼容 Windows 路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompts_dir = os.path.normpath(os.path.join(base_dir, '..', 'prompts'))
        prompt_path = os.path.join(prompts_dir, f"{role}.json")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_data = json.load(f)
            # prompt 只作为system prompt
            system = prompt_data.get("prompt") or prompt_data.get("content") or str(prompt_data)
            greeting = prompt_data.get("greeting")
    meta = _storage().create_conversation(req.title, system)
    # 创建后将greeting作为assistant消息加入
    if greeting:
        from ..schemas import Message
        _storage().append_message(meta.id, Message(role="assistant", content=greeting))
    return meta


@router.patch("/{cid}", response_model=ConversationMeta)
def rename_conversation(cid: str, payload: dict):
    title = payload.get("title")
    if not title or not isinstance(title, str):
        raise HTTPException(status_code=400, detail="title is required")
    try:
        return _storage().rename_conversation(cid, title)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")


@router.delete("/{cid}", status_code=204)
def delete_conversation(cid: str):
    try:
        _storage().delete_conversation(cid)
        return None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")


@router.get("/{cid}/messages")
def get_messages(cid: str):
    try:
        msgs = _storage().get_messages(cid)
        return {"id": cid, "messages": msgs}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="conversation not found")

