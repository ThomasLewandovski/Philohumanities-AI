from __future__ import annotations

from typing import AsyncGenerator, Dict, List

from .llm_client import LLMClient
from .role_cards import RoleCard


class OpenAICompatProvider:
    """OpenAI-compatible provider using LLMClient. If stream isn't available, it
    fetches a full completion and re-chunks locally for SSE.
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def stream_reply(
        self,
        role: RoleCard,
        history: List[Dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> AsyncGenerator[str, None]:
        # Prepend persona as system if not present
        messages = _ensure_persona_system(role, history)
        result = await self.client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        try:
            content = result["choices"][0]["message"]["content"] or ""
        except Exception:
            content = ""
        # Re-chunk for SSE delivery
        for i in range(0, len(content), 64):
            yield content[i : i + 64]


def _ensure_persona_system(role: RoleCard, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if history and history[0].get("role") == "system":
        return history
    sys = role.system_prompt
    if role.style_hints:
        sys += f"\n风格：{role.style_hints}"
    return [{"role": "system", "content": sys}] + history
