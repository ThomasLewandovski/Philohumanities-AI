from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import List

from filelock import FileLock

from .schemas import Conversation, ConversationMeta, Message


def _now() -> datetime:
    return datetime.utcnow()


class Storage:
    def __init__(self, data_dir: str) -> None:
        self.base = os.path.abspath(data_dir)
        self.index_path = os.path.join(self.base, "index.json")
        self.conv_dir = os.path.join(self.base, "conversations")
        self.locks_dir = os.path.join(self.base, ".locks")
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        os.makedirs(self.base, exist_ok=True)
        os.makedirs(self.conv_dir, exist_ok=True)
        os.makedirs(self.locks_dir, exist_ok=True)
        if not os.path.exists(self.index_path):
            self._atomic_write(self.index_path, [])

    @contextmanager
    def _lock(self, name: str):
        lock_path = os.path.join(self.locks_dir, f"{name}.lock")
        lock = FileLock(lock_path)
        with lock:
            yield

    def _atomic_write(self, path: str, data) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)

    # Index operations
    def _read_index(self) -> List[ConversationMeta]:
        with self._lock("index"):
            with open(self.index_path, "r", encoding="utf-8") as f:
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
            if os.path.exists(self._conv_path(m.id)):
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
        # write conv
        self._write_conversation(conv)
        # update index
        metas = self._read_index()
        metas.append(meta)
        self._write_index(metas)
        return meta

    # Conversation file operations
    def _conv_path(self, cid: str) -> str:
        return os.path.join(self.conv_dir, f"{cid}.json")

    @contextmanager
    def _conv_lock(self, cid: str):
        with self._lock(f"conv-{cid}"):
            yield

    def _read_conversation(self, cid: str) -> Conversation:
        path = self._conv_path(cid)
        if not os.path.exists(path):
            raise FileNotFoundError(cid)
        with self._conv_lock(cid):
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        return Conversation.model_validate(raw)

    def _write_conversation(self, conv: Conversation) -> None:
        path = self._conv_path(conv.id)
        raw = conv.model_dump(mode="json")
        with self._conv_lock(conv.id):
            self._atomic_write(path, raw)

    # Public operations
    def get_messages(self, cid: str) -> List[Message]:
        return self._read_conversation(cid).messages

    def append_message(self, cid: str, message: Message) -> Conversation:
        conv = self._read_conversation(cid)
        conv.messages.append(message)
        conv.updatedAt = _now()
        self._write_conversation(conv)
        # sync index updatedAt
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
        # remove file
        path = self._conv_path(cid)
        if os.path.exists(path):
            with self._conv_lock(cid):
                os.remove(path)
        # update index
        metas = self._read_index()
        metas = [m for m in metas if m.id != cid]
        self._write_index(metas)
