from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ...infrastructure.paths import prompts_dir


@dataclass(frozen=True)
class RoleCard:
    slug: str
    name: str
    system_prompt: str
    style_hints: Optional[str] = None
    greeting: Optional[str] = None
    locales: Optional[List[str]] = None


class RoleCardRegistry:
    """Load role cards from backend/prompts/*.json

    A role card file minimal schema:
      { "name": "马克思", "prompt": "system role prompt" }

    Optional fields:
      - style: additional style hints
      - greeting: optional first message suggestion
      - locales: ["zh-CN", "en"]
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        base_path = Path(base_dir) if base_dir else prompts_dir()
        self.prompts_dir = base_path
        self._cache: Dict[str, RoleCard] = {}
        self._load()

    def _load(self) -> None:
        if not self.prompts_dir.is_dir():
            return
        for file_path in self.prompts_dir.iterdir():
            if file_path.suffix.lower() != ".json":
                continue
            slug = file_path.stem
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            name = str(data.get("name") or slug)
            prompt = str(data.get("prompt") or data.get("system") or "").strip()
            if not prompt:
                continue
            style = None
            if isinstance(data.get("style"), str):
                style = data["style"].strip()
            greeting = None
            if isinstance(data.get("greeting"), str):
                greeting = data["greeting"].strip()
            locales = data.get("locales") if isinstance(data.get("locales"), list) else None
            self._cache[slug] = RoleCard(
                slug=slug,
                name=name,
                system_prompt=prompt,
                style_hints=style,
                greeting=greeting,
                locales=locales,
            )

    def list(self) -> List[RoleCard]:
        return sorted(self._cache.values(), key=lambda r: r.slug)

    def get(self, slug: str) -> Optional[RoleCard]:
        return self._cache.get(slug)
