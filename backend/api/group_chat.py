from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from ..app.dependencies import (
    get_group_storage,
    get_llm_client,
    get_provider_registry,
    get_settings,
)
from ..core.groups.repository import GroupStorage
from ..core.llm.client import LLMClient
from ..core.llm.streams import OpenAICompatProvider
from ..core.roles.registry import RoleCardRegistry
from ..infrastructure.paths import ensure_dir, resolve_data_dir


router = APIRouter(prefix="/api", tags=["group-chat"])


def _gstore() -> GroupStorage:
    return get_group_storage()


def _registry() -> RoleCardRegistry:
    return RoleCardRegistry()


def _provider_for(alias: Optional[str]) -> OpenAICompatProvider:
    preg = get_provider_registry()
    acc = preg.get(alias)
    if not acc:
        raise HTTPException(status_code=500, detail="no provider available")
    client = LLMClient(base_url=acc.base_url, api_key=acc.api_key, default_model=acc.default_model)
    return OpenAICompatProvider(client)


@router.get("/group-conversations")
def list_group_conversations():
    return _gstore().list()


@router.post("/group-conversations")
def create_group_conversation(payload: Dict[str, Any]):
    participants = payload.get("participants")
    title = (payload.get("title") or "").strip() or None
    if not isinstance(participants, list) or not participants:
        raise HTTPException(status_code=400, detail="participants is required")
    if len(participants) > 3:
        raise HTTPException(status_code=400, detail="at most 3 participants are allowed")
    # validate roleCardId exists
    reg = _registry()
    for p in participants:
        slug = p.get("roleCardId")
        if not isinstance(slug, str) or not reg.get(slug):
            raise HTTPException(status_code=400, detail=f"invalid roleCardId: {slug}")
    # assign providerAlias if missing using providers.json accounts (exclude env-derived defaults)
    preg = get_provider_registry()
    file_accounts = [a for a in preg.list() if not a.alias.startswith("default")]
    for idx, p in enumerate(participants):
        if not p.get("providerAlias"):
            acc = file_accounts[idx % len(file_accounts)] if file_accounts else None
            if acc:
                p["providerAlias"] = acc.alias
    # Auto-generate a friendly Chinese title if not provided: 与A、B、C的对话
    if not title:
        names: List[str] = []
        for p in participants:
            slug = p.get("roleCardId")
            rc = reg.get(slug) if isinstance(slug, str) else None
            nm = (p.get("name") or (rc.name if rc else slug) or "").strip()
            if nm:
                names.append(nm)
        if names:
            joined = "、".join(names[:3])
            title = f"与{joined}的对话"
        else:
            title = "群聊会话"

    gs = _gstore()
    meta = gs.create_conversation(title, participants)
    return meta


@router.get("/group-conversations/{gid}")
def get_group(gid: str):
    try:
        return _gstore().get(gid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="group conversation not found")


def _referee_log_write(gid: str, turn: int, obj: Dict[str, Any]) -> None:
    # write to data/referee_log/<gid>/turn_<n>.jsonl
    s = get_settings()
    base = resolve_data_dir(s.data_dir) / "referee_log" / gid
    ensure_dir(base)
    path = base / f"turn_{turn}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _judge_client() -> LLMClient:
    return get_llm_client()


async def _sse_round(gid: str, text: Optional[str]) -> AsyncGenerator[bytes, None]:
    reg = _registry()
    gs = _gstore()
    try:
        conv = gs.get(gid)
    except FileNotFoundError:
        yield _sse_event("error", {"code": "not_found", "message": "group conversation not found"})
        return

    # append user message if provided
    if isinstance(text, str) and text.strip():
        gs.append_user(gid, text)
        conv = gs.get(gid)

    participants: List[Dict[str, Any]] = conv.get("participants", [])
    if not participants:
        yield _sse_event("error", {"code": "no_participants", "message": "no participants"})
        return

    yield _sse_event(
        "status.start",
        {
            "conversationId": gid,
            "agents": [
                {
                    "agentId": p["agentId"],
                    "roleCardId": p["roleCardId"],
                    "name": p.get("name") or p["roleCardId"],
                    "model": p.get("model") or "",
                    "providerAlias": p.get("providerAlias") or "",
                }
                for p in participants
            ],
        },
    )

    # Orchestrator config
    orch = conv.get("orchestrator") or {}
    allow_repeated = bool(orch.get("allowRepeated") is True)
    max_attempts = int(orch.get("maxSelectorAttempts") or 1)

    last_speaker = conv.get("lastSpeaker")
    candidates = [p["agentId"] for p in participants]
    if not allow_repeated and last_speaker in candidates and len(candidates) > 1:
        candidates = [c for c in candidates if c != last_speaker]

    # Judge selection only when >=2 candidates; else pick the only one
    chosen: Optional[str] = None
    reason = None
    attempts = 0
    yield _sse_event("judge.start", {"candidates": candidates, "allowRepeated": allow_repeated, "attempts": max_attempts})

    override_next = (conv.get("orchestrator") or {}).get("overrideNext")
    if isinstance(override_next, str) and override_next in [p["agentId"] for p in participants]:
        chosen = override_next
        reason = "override_next"
        # clear override
        gs.update_orchestrator(gid, {"overrideNext": None})
    elif len(candidates) == 1:
        chosen = candidates[0]
        reason = "single_candidate"
    else:
        judge_client = _judge_client()
        # Build judge prompt
        lines = []
        # participants roles summary
        for p in participants:
            slug = p["roleCardId"]
            rc = reg.get(slug)
            if not rc:
                continue
            desc = rc.style_hints or "角色"
            lines.append(f"{p['agentId']}: {rc.name} - {desc}")
        roles_block = "\n".join(lines)
        # history compact
        hlines = []
        for m in conv.get("messages", [])[-6:]:
            src = m.get("agentId") if m.get("agentId") else m.get("role")
            hlines.append(f"{src}: {m['content']}")
        history_block = "\n".join(hlines)
        participants_list = ", ".join(candidates)
        base_prompt = (
            "你是群聊的判官。请仅从候选人中选择下一位发言者的agentId，严格只输出那个agentId，不要其他内容。\n"
            f"候选: [{participants_list}]\n不允许连续发言: {'是' if not allow_repeated else '否'}；上一位: {last_speaker or '无'}\n"
            f"角色列表:\n{roles_block}\n\n最近历史:\n{history_block}\n"
        )
        while attempts < max_attempts:
            attempts += 1
            # call judge
            messages = [{"role": "user", "content": base_prompt}]
            jresp = await judge_client.chat_completion(messages=messages, stream=False, max_tokens=16)
            raw = ""
            try:
                raw = jresp["choices"][0]["message"]["content"].strip()
            except Exception:
                raw = ""
            log_entry = {"attempt": attempts, "prompt": base_prompt, "raw": raw, "candidates": candidates, "last": last_speaker}
            _referee_log_write(gid, int(conv.get("turn") or 0) + 1, log_entry)
            # normalize
            out = raw.strip().strip("` ")
            # accept if exact match to candidate
            if out in candidates:
                chosen = out
                reason = "judge_ok"
                break
            # try match by roleCard name or display name
            lower = out.lower()
            for p in participants:
                if p["agentId"] in candidates:
                    if lower in (p.get("name") or "").lower() or lower == p["roleCardId"].lower():
                        if (not allow_repeated) and p["agentId"] == last_speaker:
                            yield _sse_event("judge.feedback", {"text": "不能选择与上一位相同的发言者"})
                            break
                        chosen = p["agentId"]
                        reason = "judge_name_match"
                        break
            if chosen:
                break
            yield _sse_event("judge.feedback", {"text": "输出不合法，请只输出一个候选 agentId。"})
        if not chosen:
            # fallback round-robin
            order = [p["agentId"] for p in participants]
            if last_speaker and last_speaker in order:
                idx = (order.index(last_speaker) + 1) % len(order)
            else:
                idx = 0
            # ensure idx points into candidates list
            rr = order[idx]
            if (not allow_repeated) and rr == last_speaker and len(candidates) > 1:
                rr = candidates[0]
            chosen = rr
            reason = "fallback_round_robin"

    yield _sse_event("judge.decision", {"agentId": chosen, "reason": reason})

    # Produce chosen agent's message
    chosen_p = next((p for p in participants if p["agentId"] == chosen), None)
    if not chosen_p:
        yield _sse_event("error", {"code": "chosen_not_found", "message": "chosen agent not found"})
        return
    slug = chosen_p["roleCardId"]
    rc = reg.get(slug)
    provider = _provider_for(chosen_p.get("providerAlias"))
    model = chosen_p.get("model")

    history = []
    sys = rc.system_prompt + (f"\n风格：{rc.style_hints}" if rc.style_hints else "")
    history.append({"role": "system", "content": sys})
    for m in conv.get("messages", []):
        history.append({"role": m["role"], "content": m["content"]})

    message_id = f"{chosen}-{int(time.time()*1000)}"
    yield _sse_event("agent.message.created", {"agentId": chosen, "messageId": message_id})
    chunks: List[str] = []
    async for delta in provider.stream_reply(rc, history, model=model):
        chunks.append(delta)
        yield _sse_event("agent.message.delta", {"agentId": chosen, "messageId": message_id, "delta": delta})
    final_text = "".join(chunks)
    gs.append_assistant(gid, chosen, final_text)
    gs.set_last_speaker(gid, chosen)
    turn_no = gs.bump_turn(gid)
    yield _sse_event("agent.message.completed", {"agentId": chosen, "messageId": message_id, "usage": {"promptTokens": 0, "completionTokens": len(final_text)//4}, "finishReason": "stop", "turn": turn_no})

    # if paused, emit status.paused
    conv2 = gs.get(gid)
    if conv2.get("paused"):
        yield _sse_event("status.paused", {"conversationId": gid})
    yield b"event: done\n\n"


def _sse_event(event: str, data: Dict[str, Any]) -> bytes:
    return f"event: {event}\n".encode() + f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@router.post("/group-conversations/{gid}/assistant/stream")
async def group_round(gid: str, payload: Dict[str, Any]):
    text = payload.get("text")
    gen = _sse_round(gid, text if isinstance(text, str) else None)
    return StreamingResponse(gen, media_type="text/event-stream")


@router.post("/group-conversations/{gid}/pause")
def pause_group(gid: str, payload: Dict[str, Any] | None = None):
    try:
        conv = _gstore().set_paused(gid, True)
        return {"id": gid, "paused": conv.get("paused")}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="group conversation not found")


@router.post("/group-conversations/{gid}/resume")
def resume_group(gid: str):
    try:
        conv = _gstore().set_paused(gid, False)
        return {"id": gid, "paused": conv.get("paused")}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="group conversation not found")


@router.post("/group-conversations/{gid}/user")
def user_insert(gid: str, payload: Dict[str, Any]):
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    try:
        _gstore().append_user(gid, text)
        return {"ok": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="group conversation not found")


@router.post("/group-conversations/{gid}/override-next")
def override_next(gid: str, payload: Dict[str, Any]):
    # Minimal: store in orchestrator as a temp hint; for MVP, front-end can send text with override handled on client side.
    agent_id = payload.get("agentId")
    if not isinstance(agent_id, str):
        raise HTTPException(status_code=400, detail="agentId is required")
    try:
        conv = _gstore().get(gid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="group conversation not found")
    # Validate agent exists
    if agent_id not in [p["agentId"] for p in conv.get("participants", [])]:
        raise HTTPException(status_code=400, detail="agentId not in participants")
    # Store hint
    _gstore().update_orchestrator(gid, {"overrideNext": agent_id})
    return {"ok": True, "agentId": agent_id}
