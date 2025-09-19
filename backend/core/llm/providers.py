from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from ...infrastructure.paths import resolve_data_dir
from ..settings import get_settings


@dataclass(frozen=True)
class ProviderAccount:
    alias: str
    base_url: str
    api_key: Optional[str]
    default_model: Optional[str] = None
    priority: int = 0


class ProviderRegistry:
    """Loads provider accounts from DATA_DIR/providers.json if present.

    Fallback: derive a single 'default' provider from environment settings.
    Schema of providers.json:
      { "accounts": [
          {"alias": "openai_a", "base_url": "https://api.openai.com", "api_key": "sk-...", "default_model": "gpt-4o-mini", "priority": 10}
        ] }
    """

    def __init__(self) -> None:
        s = get_settings()
        self.data_dir = resolve_data_dir(s.data_dir)
        self.path = self.data_dir / "providers.json"
        self._cache: Dict[str, ProviderAccount] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                accounts = raw.get("accounts", [])
                for acc in accounts:
                    alias = str(acc.get("alias") or "").strip()
                    base_url = str(acc.get("base_url") or "").strip().rstrip("/")
                    if not alias or not base_url:
                        continue
                    api_key = acc.get("api_key") or None
                    default_model = acc.get("default_model") or None
                    prio = int(acc.get("priority") or 0)
                    self._cache[alias] = ProviderAccount(alias, base_url, api_key, default_model, prio)
            except Exception:
                self._cache.clear()

        s = get_settings()
        if s.llm_base_url:
            alias = "default"
            if alias in self._cache:
                alias = "default_env"
            max_priority = max([acc.priority for acc in self._cache.values()] + [0]) + 1
            self._cache[alias] = ProviderAccount(
                alias=alias,
                base_url=s.llm_base_url,
                api_key=s.llm_api_key,
                default_model=s.llm_model,
                priority=max_priority,
            )

    def list(self) -> List[ProviderAccount]:
        return sorted(self._cache.values(), key=lambda a: (-a.priority, a.alias))

    def get(self, alias: Optional[str]) -> Optional[ProviderAccount]:
        if not alias:
            items = self.list()
            return items[0] if items else None
        return self._cache.get(alias)
