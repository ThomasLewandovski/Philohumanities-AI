from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List

from filelock import FileLock

from ...infrastructure.paths import ensure_dir, resolve_data_dir
from .models import Conversation, ConversationMeta, Message


def _now() -> datetime:
    return datetime.utcnow()


class Storage:
    def __init__(self, data_dir: str) -> None:
        self.base = resolve_data_dir(data_dir)
        self.index_path = self.base / "index.json"
        self.conv_dir = self.base / "conversations"
        self.locks_dir = self.base / ".locks"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        ensure_dir(self.base)
        ensure_dir(self.conv_dir)
        ensure_dir(self.locks_dir)
        if not self.index_path.exists():
            self._atomic_write(self.index_path, [])

    @contextmanager
    def _lock(self, name: str):
        lock_path = self.locks_dir / f"{name}.lock"
        lock = FileLock(str(lock_path))
        with lock:
            yield

    def _atomic_write(self, path: Path, data) -> None:
        tmp = path.with_name(f"{path.name}.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        tmp.replace(path)

    # Index operations
    def _read_index(self) -> List[ConversationMeta]:
        with self._lock("index"):
            with self.index_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        return [ConversationMeta.model_validate(i) for i in raw]

    def _write_index(self, metas: List[ConversationMeta]) -> None:
        raw = [m.model_dump(mode="json") for m in metas]
        with self._lock("index"):
            self._atomic_write(self.index_path, raw)

    def list_conversations(self) -> List[ConversationMeta]:
        metas = self._read_index()
        # Filter out stale entries whose files were removed externally
        valid: List[ConversationMeta] = []
        changed = False
        for m in metas:
            if self._conv_path(m.id).exists():
                valid.append(m)
            else:
                changed = True
        if changed:
            # Auto-heal index if we detected missing conversation files
            self._write_index(valid)
        valid.sort(key=lambda m: m.updatedAt, reverse=True)
        return valid

    def create_conversation(self, title: str | None, system: str | None) -> ConversationMeta:
        cid = str(uuid.uuid4())
        now = _now()
        meta = ConversationMeta(id=cid, title=title or "新的会话", createdAt=now, updatedAt=now)
        conv = Conversation(id=cid, title=meta.title, createdAt=now, updatedAt=now, messages=[])
        if system:
            conv.messages.append(Message(role="system", content=system, ts=now))
        self._write_conversation(conv)
        metas = self._read_index()
        metas.append(meta)
        self._write_index(metas)
        return meta

    def _conv_path(self, cid: str) -> Path:
        return self.conv_dir / f"{cid}.json"

    @contextmanager
    def _conv_lock(self, cid: str):
        with self._lock(f"conv-{cid}"):
            yield

    def _read_conversation(self, cid: str) -> Conversation:
        path = self._conv_path(cid)
        if not path.exists():
            raise FileNotFoundError(cid)
        with self._conv_lock(cid):
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        return Conversation.model_validate(raw)

    def _write_conversation(self, conv: Conversation) -> None:
        path = self._conv_path(conv.id)
        raw = conv.model_dump(mode="json")
        with self._conv_lock(conv.id):
            self._atomic_write(path, raw)

    def get_messages(self, cid: str) -> List[Message]:
        return self._read_conversation(cid).messages

    def append_message(self, cid: str, message: Message) -> Conversation:
        conv = self._read_conversation(cid)
        conv.messages.append(message)
        conv.updatedAt = _now()
        self._write_conversation(conv)
        metas = self._read_index()
        for m in metas:
            if m.id == cid:
                m.updatedAt = conv.updatedAt
                break
        self._write_index(metas)
        return conv

    def rename_conversation(self, cid: str, title: str) -> ConversationMeta:
        conv = self._read_conversation(cid)
        conv.title = title
        conv.updatedAt = _now()
        self._write_conversation(conv)
        metas = self._read_index()
        for m in metas:
            if m.id == cid:
                m.title = title
                m.updatedAt = conv.updatedAt
                break
        self._write_index(metas)
        return ConversationMeta(id=conv.id, title=conv.title, createdAt=conv.createdAt, updatedAt=conv.updatedAt)

    def delete_conversation(self, cid: str) -> None:
        path = self._conv_path(cid)
        if path.exists():
            with self._conv_lock(cid):
                path.unlink()
        metas = self._read_index()
        metas = [m for m in metas if m.id != cid]
        self._write_index(metas)
