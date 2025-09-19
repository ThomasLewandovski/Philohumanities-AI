from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...infrastructure.paths import ensure_dir, resolve_data_dir
from ..conversations.repository import Storage
from ..llm.client import LLMClient
from ..settings import get_settings


def _data_paths() -> Tuple[Path, Path]:
    s = get_settings()
    base = resolve_data_dir(s.data_dir) / "suggestions"
    ensure_dir(base)
    cache_path = base / "cache.json"
    if not cache_path.exists():
        cache_path.write_text("{}", encoding="utf-8")
    return base, cache_path


def _load_cache() -> Dict[str, Any]:
    _, path = _data_paths()
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    _, path = _data_paths()
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _limit_sentences(text: str, max_sentences: int = 2) -> str:
    parts = re.split(r"([。！？!?]|\n)+", text.strip())
    out = []
    sentences = 0
    for i in range(0, len(parts), 2):
        segment = parts[i].strip()
        ending = parts[i + 1] if i + 1 < len(parts) else ""
        if not segment:
            continue
        out.append(segment + ending)
        sentences += 1
        if sentences >= max_sentences:
            break
    return (" ".join(out)).strip()


def _dedup_texts(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    res: List[Dict[str, str]] = []
    for it in items:
        key = (it.get("text") or "").strip()
        norm = re.sub(r"\s+", "", key.lower())[:40]
        if not norm or norm in seen:
            continue
        seen.add(norm)
        res.append(it)
    return res


async def generate_suggestions(
    cid: str,
    k: int = 4,
    max_sentences: int = 2,
    angles: List[str] | None = None,
    locale: str | None = None,
    diversify: bool = False,
) -> Dict[str, Any]:
    s = get_settings()
    st = Storage(s.data_dir)
    msgs = st.get_messages(cid)
    last_id = f"{len(msgs)}"
    key_src = json.dumps({"cid": cid, "last": last_id, "k": k, "angles": angles, "locale": locale}, ensure_ascii=False)
    cache_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()[:24]
    cache = _load_cache()
    if (not diversify) and cache_key in cache:
        return cache[cache_key]

    system = next((m.content for m in msgs if m.role == "system"), None)
    tail = []
    for m in msgs[-6:]:
        if m.role in ("user", "assistant"):
            tail.append({"role": m.role, "content": m.content})

    sys_prompt = (
        "你是‘AI小智囊’，任务是基于对话历史，为用户提供下一条发言的简短备选项。"
        "要求：1) 只输出 JSON 数组，长度为{K}；2) 每项对象含 text 与 angle；3) text 不超过{SENT}句，语言与上下文一致；"
        "4) 角度需彼此不同（如 clarify/ask-example/relate/contrast/synthesize/propose/challenge）；"
        "5) 至少包含一个非疑问句（如总结/建议/承接陈述）；6) 不要输出额外文字。"
    ).replace("{K}", str(k)).replace("{SENT}", str(max_sentences))

    user_prompt = "请基于以下对话历史，给出下一条用户可以发送的{K}个不同角度的简短选项：\n".replace("{K}", str(k))
    if angles:
        user_prompt += f"优先考虑这些角度：{', '.join(angles)}。\n"
    context_lines: List[str] = []
    if system:
        context_lines.append(f"[persona] {system}")
    last_assistant = None
    for m in reversed(msgs):
        if m.role == "assistant":
            last_assistant = m.content
            break
    if last_assistant:
        context_lines.append(f"[last_assistant] {last_assistant}")
    for m in tail:
        context_lines.append(f"[{m['role']}] {m['content']}")
    user_prompt += "\n".join(context_lines)
    user_prompt += "\n严格输出JSON数组，例如: [{\"text\":\"...\",\"angle\":\"clarify\"}, ...]"

    client = LLMClient(base_url=s.llm_base_url, api_key=s.llm_api_key, default_model=s.llm_model)
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
    resp = await client.chat_completion(messages=messages, stream=False, max_tokens=256)
    try:
        content = resp["choices"][0]["message"]["content"] or "[]"
    except Exception:
        content = "[]"

    suggestions: List[Dict[str, str]] = []
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            for it in parsed:
                if not isinstance(it, dict):
                    continue
                text = str(it.get("text") or "").strip()
                angle = str(it.get("angle") or "").strip() or "other"
                if text:
                    suggestions.append({"text": _limit_sentences(text, max_sentences), "angle": angle})
    except Exception:
        suggestions = []

    suggestions = _dedup_texts(suggestions)[:k]
    result = {
        "suggestions": suggestions,
        "meta": {
            "model": s.llm_model,
            "promptVersion": 1,
            "cached": False,
        },
    }
    cache[cache_key] = result | {"meta": {**result["meta"], "cached": True}}
    _save_cache(cache)
    return result
