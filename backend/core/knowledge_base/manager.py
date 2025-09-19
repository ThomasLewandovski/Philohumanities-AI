from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...infrastructure.paths import ensure_dir, resolve_data_dir
from ..settings import get_settings


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
    """Simple KB manager: stores KBs and documents on filesystem."""

    def __init__(self) -> None:
        s = get_settings()
        base = resolve_data_dir(s.data_dir) / "kb"
        ensure_dir(base)
        self.base = base
        self.index_path = self.base / "index.json"
        self.bindings_path = self.base / "bindings.json"
        if not self.index_path.exists():
            self._write(self.index_path, [])
        if not self.bindings_path.exists():
            self._write(self.bindings_path, {})

    def _write(self, path: Path, data: Any) -> None:
        tmp = path.with_name(f"{path.name}.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    def _read(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8") as f:
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
        kb_dir = self.base / kb_id
        docs_dir = kb_dir / "docs"
        ensure_dir(docs_dir)
        self._write(kb_dir / "meta.json", meta)
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
        path = self.base / kb_id / "meta.json"
        if not path.exists():
            return None
        return self._read(path)

    def ingest_text(self, kb_id: str, title: str, text: str) -> Dict[str, Any]:
        kb_dir = self.base / kb_id
        docs_dir = kb_dir / "docs"
        if not kb_dir.exists():
            raise FileNotFoundError(kb_id)

        ensure_dir(docs_dir)
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
        self._write(docs_dir / f"{doc_id}.json", doc)

        meta_path = kb_dir / "meta.json"
        meta = self._read(meta_path)
        meta["updatedAt"] = _now()
        self._write(meta_path, meta)

        return doc

    def list_docs(self, kb_id: str) -> List[Dict[str, Any]]:
        docs_dir = self.base / kb_id / "docs"
        if not docs_dir.exists():
            return []
        docs: List[Dict[str, Any]] = []
        for file_path in docs_dir.iterdir():
            if file_path.suffix != ".json":
                continue
            docs.append(self._read(file_path))
        docs.sort(key=lambda d: d.get("createdAt", ""), reverse=True)
        return docs
