from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import get_settings


def _now() -> str:
    return datetime.utcnow().isoformat()


@dataclass
class KBMeta:
    id: str
    title: str
    createdAt: str
    updatedAt: str
    roleCardId: Optional[str] = None


class KnowledgeBaseManager:
    """Simple KB manager: stores KBs and documents on filesystem.

    Layout under DATA_DIR/kb/
      - index.json                            # list of KB metas
      - bindings.json                         # { roleCardId: [kbId, ...] }
      - <kbId>/meta.json                      # meta
      - <kbId>/docs/<docId>.json              # structured doc with chunks
    """

    def __init__(self) -> None:
        s = get_settings()
        self.base = os.path.join(os.path.abspath(s.data_dir), "kb")
        os.makedirs(self.base, exist_ok=True)
        self.index_path = os.path.join(self.base, "index.json")
        self.bindings_path = os.path.join(self.base, "bindings.json")
        if not os.path.exists(self.index_path):
            self._write(self.index_path, [])
        if not os.path.exists(self.bindings_path):
            self._write(self.bindings_path, {})

    def _write(self, path: str, data: Any) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _read(self, path: str) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def create_kb(self, title: str, roleCardId: Optional[str] = None) -> Dict[str, Any]:
        kb_id = str(uuid.uuid4())
        meta = {
            "id": kb_id,
            "title": title or "未命名知识库",
            "createdAt": _now(),
            "updatedAt": _now(),
            "roleCardId": roleCardId,
        }
        kb_dir = os.path.join(self.base, kb_id)
        os.makedirs(os.path.join(kb_dir, "docs"), exist_ok=True)
        self._write(os.path.join(kb_dir, "meta.json"), meta)
        idx = self._read(self.index_path)
        idx.append(meta)
        self._write(self.index_path, idx)
        if roleCardId:
            bindings = self._read(self.bindings_path)
            arr = bindings.get(roleCardId, [])
            if kb_id not in arr:
                arr.append(kb_id)
            bindings[roleCardId] = arr
            self._write(self.bindings_path, bindings)
        return meta

    def list_kb(self) -> List[Dict[str, Any]]:
        return sorted(self._read(self.index_path), key=lambda x: x["updatedAt"], reverse=True)

    def list_role_kb(self, roleCardId: str) -> List[Dict[str, Any]]:
        bindings = self._read(self.bindings_path)
        ids = bindings.get(roleCardId, [])
        metas = [self.get_kb(i) for i in ids]
        return [m for m in metas if m]

    def get_kb(self, kb_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self.base, kb_id, "meta.json")
        if not os.path.exists(path):
            return None
        return self._read(path)

    def ingest_text(self, kb_id: str, title: str, text: str) -> Dict[str, Any]:
        kb_dir = os.path.join(self.base, kb_id)
        if not os.path.exists(kb_dir):
            raise FileNotFoundError(kb_id)
        # simple structuring: paragraphs -> chunks, naive headings detection
        lines = [l.strip() for l in text.splitlines()]
        paragraphs: List[str] = []
        buf: List[str] = []
        for ln in lines:
            if not ln:
                if buf:
                    paragraphs.append(" ".join(buf))
                    buf = []
            else:
                buf.append(ln)
        if buf:
            paragraphs.append(" ".join(buf))

        def is_heading(p: str) -> bool:
            return bool(re.match(r"^(第[一二三四五六七八九十百千]+[章节部篇]|[0-9]+[\.|、\)]|[#]{1,6}\s)", p)) or len(p) < 40

        chunks: List[Dict[str, Any]] = []
        outline: List[str] = []
        for i, p in enumerate(paragraphs, 1):
            kind = "heading" if is_heading(p) else "paragraph"
            if kind == "heading":
                outline.append(p[:80])
            chunks.append({"index": i, "type": kind, "text": p})

        summary = (paragraphs[0][:200] if paragraphs else "").strip()
        doc_id = str(uuid.uuid4())
        doc = {
            "id": doc_id,
            "title": title or f"文档-{doc_id[:8]}",
            "createdAt": _now(),
            "outline": outline[:20],
            "summary": summary,
            "chunks": chunks,
        }
        self._write(os.path.join(kb_dir, "docs", f"{doc_id}.json"), doc)

        # touch meta updatedAt
        meta_path = os.path.join(kb_dir, "meta.json")
        meta = self._read(meta_path)
        meta["updatedAt"] = _now()
        self._write(meta_path, meta)

        return doc

    def list_docs(self, kb_id: str) -> List[Dict[str, Any]]:
        kb_dir = os.path.join(self.base, kb_id)
        docs_dir = os.path.join(kb_dir, "docs")
        if not os.path.exists(docs_dir):
            return []
        docs: List[Dict[str, Any]] = []
        for fn in os.listdir(docs_dir):
            if fn.endswith(".json"):
                docs.append(self._read(os.path.join(docs_dir, fn)))
        docs.sort(key=lambda d: d.get("createdAt", ""), reverse=True)
        return docs

