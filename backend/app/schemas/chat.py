from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
import uuid as _uuid  # noqa: F401


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: UUID
    timestamp: datetime


class ChatResponse(BaseModel):
    session_id: UUID
    reply: str
    messages: list[ChatMessage]
    request_id: str = ""
