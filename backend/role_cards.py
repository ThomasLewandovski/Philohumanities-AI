from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


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
        here = os.path.dirname(__file__)
        self.prompts_dir = base_dir or os.path.join(here, "prompts")
        self._cache: Dict[str, RoleCard] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.isdir(self.prompts_dir):
            return
        for fname in os.listdir(self.prompts_dir):
            if not fname.lower().endswith(".json"):
                continue
            slug = os.path.splitext(fname)[0]
            path = os.path.join(self.prompts_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
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

