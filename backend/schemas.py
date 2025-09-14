from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str
    ts: datetime = Field(default_factory=lambda: datetime.utcnow())


class ConversationMeta(BaseModel):
    id: str
    title: str
    createdAt: datetime
    updatedAt: datetime


class Conversation(BaseModel):
    id: str
    title: str
    createdAt: datetime
    updatedAt: datetime
    messages: List[Message] = Field(default_factory=list)


class CreateConversationReq(BaseModel):
    title: Optional[str] = None
    system: Optional[str] = None


class SendMessageReq(BaseModel):
    content: str
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class SendMessageResp(BaseModel):
    assistant: Message

