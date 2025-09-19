from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from filelock import FileLock

from ...infrastructure.paths import ensure_dir, resolve_data_dir


def _now() -> datetime:
    return datetime.utcnow()


@dataclass
class GroupParticipant:
    agentId: str
    roleCardId: str
    name: str
    model: Optional[str] = None
    providerAlias: Optional[str] = None


@dataclass
class GroupMessage:
    role: str  # user|assistant|system
    content: str
    ts: datetime
    agentId: Optional[str] = None  # for assistant messages


@dataclass
class GroupConversation:
    id: str
    title: str
    createdAt: datetime
    updatedAt: datetime
    participants: List[GroupParticipant]
    messages: List[GroupMessage]


class GroupStorage:
    def __init__(self, data_dir: str) -> None:
        base = resolve_data_dir(data_dir)
        self.root = base / "group"
        self.index_path = self.root / "index.json"
        self.conv_dir = self.root / "conversations"
        self.locks_dir = self.root / ".locks"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        ensure_dir(self.root)
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

    def _read_index(self) -> List[Dict[str, Any]]:
        with self._lock("index"):
            with self.index_path.open("r", encoding="utf-8") as f:
                return json.load(f)

    def _write_index(self, items: List[Dict[str, Any]]) -> None:
        with self._lock("index"):
            self._atomic_write(self.index_path, items)

    def _conv_path(self, gid: str) -> Path:
        return self.conv_dir / f"{gid}.json"

    @contextmanager
    def _conv_lock(self, gid: str):
        with self._lock(f"conv-{gid}"):
            yield

    def create_conversation(self, title: Optional[str], participants: List[Dict[str, Any]]) -> Dict[str, Any]:
        gid = str(uuid.uuid4())
        now = _now()
        parts: List[Dict[str, Any]] = []
        for i, p in enumerate(participants):
            agent_id = p.get("agentId") or f"agent-{i+1}"
            parts.append(
                {
                    "agentId": agent_id,
                    "roleCardId": p["roleCardId"],
                    "name": p.get("name") or p["roleCardId"],
                    "model": p.get("model"),
                    "providerAlias": p.get("providerAlias"),
                }
            )
        conv = {
            "id": gid,
            "title": title or "群聊会话",
            "createdAt": now,
            "updatedAt": now,
            "participants": parts,
            "messages": [],
            "orchestrator": {
                "mode": "selector",
                "allowRepeated": False,
                "maxSelectorAttempts": 1,
            },
            "lastSpeaker": None,
            "paused": False,
            "turn": 0,
        }
        self._write_conv(conv)
        idx = self._read_index()
        idx.append({"id": gid, "title": conv["title"], "createdAt": now, "updatedAt": now})
        self._write_index(idx)
        return {"id": gid, "title": conv["title"], "createdAt": now, "updatedAt": now, "participants": parts}

    def _write_conv(self, conv: Dict[str, Any]) -> None:
        path = self._conv_path(conv["id"])
        with self._conv_lock(conv["id"]):
            self._atomic_write(path, conv)

    def _read_conv(self, gid: str) -> Dict[str, Any]:
        path = self._conv_path(gid)
        if not path.exists():
            raise FileNotFoundError(gid)
        with self._conv_lock(gid):
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)

    def get(self, gid: str) -> Dict[str, Any]:
        return self._read_conv(gid)

    def list(self) -> List[Dict[str, Any]]:
        items = self._read_index()
        items.sort(key=lambda x: x["updatedAt"], reverse=True)
        return items

    def append_user(self, gid: str, text: str) -> None:
        conv = self._read_conv(gid)
        conv["messages"].append({"role": "user", "content": text, "ts": _now(), "agentId": None})
        conv["updatedAt"] = _now()
        self._write_conv(conv)

    def append_assistant(self, gid: str, agent_id: str, text: str) -> None:
        conv = self._read_conv(gid)
        conv["messages"].append({"role": "assistant", "content": text, "ts": _now(), "agentId": agent_id})
        conv["updatedAt"] = _now()
        self._write_conv(conv)

    def set_paused(self, gid: str, paused: bool) -> Dict[str, Any]:
        conv = self._read_conv(gid)
        conv["paused"] = bool(paused)
        conv["updatedAt"] = _now()
        self._write_conv(conv)
        return conv

    def set_last_speaker(self, gid: str, agent_id: Optional[str]) -> Dict[str, Any]:
        conv = self._read_conv(gid)
        conv["lastSpeaker"] = agent_id
        conv["updatedAt"] = _now()
        self._write_conv(conv)
        return conv

    def bump_turn(self, gid: str) -> int:
        conv = self._read_conv(gid)
        conv["turn"] = int(conv.get("turn") or 0) + 1
        conv["updatedAt"] = _now()
        self._write_conv(conv)
        return conv["turn"]

    def update_orchestrator(self, gid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        conv = self._read_conv(gid)
        orch = conv.get("orchestrator") or {}
        orch.update({k: v for k, v in patch.items() if v is not None})
        conv["orchestrator"] = orch
        conv["updatedAt"] = _now()
        self._write_conv(conv)
        return conv
