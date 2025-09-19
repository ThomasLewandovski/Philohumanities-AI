import os
from typing import Any, Dict, List, Optional

import httpx


class LLMClient:
    """Thin wrapper around an OpenAI-compatible Chat Completions API.

    Expects environment variables:
      - LLM_BASE_URL (e.g., http://localhost:8001)
      - LLM_API_KEY  (optional)
      - LLM_MODEL    (e.g., qwen2, llama3)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.default_model = default_model or os.getenv("LLM_MODEL") or ""
        self._timeout = timeout

        if not self.base_url:
            raise RuntimeError("LLM_BASE_URL is not set")

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        extra: Optional[Dict[str, Any]] = None,
        base_url_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calls the /v1/chat/completions endpoint (non-stream by default)."""

        base = (base_url_override or self.base_url).rstrip("/")
        url = f"{base}/v1/chat/completions"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        key = api_key_override or self.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"

        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if extra:
            payload.update(extra)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
