from pydantic import BaseModel, Field


class MessageIn(BaseModel):
    channel: str = Field(..., examples=["web", "whatsapp"])
    user_id: str
    text: str
    metadata: dict = Field(default_factory=dict)


class MessageOut(BaseModel):
    reply: str
    intent: str
    agent: str
    session_id: str
    trace_id: str
