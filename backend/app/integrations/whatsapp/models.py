from pydantic import BaseModel
from typing import Literal


class WATextMessage(BaseModel):
    body: str


class WAIncomingMessage(BaseModel):
    id: str
    from_: str
    type: Literal["text", "image", "audio", "document", "button", "interactive"]
    text: WATextMessage | None = None

    class Config:
        populate_by_name = True
        fields = {"from_": "from"}


class WAWebhookValue(BaseModel):
    messages: list[WAIncomingMessage] | None = None


class WAWebhookChange(BaseModel):
    field: str
    value: WAWebhookValue


class WAWebhookEntry(BaseModel):
    id: str
    changes: list[WAWebhookChange]


class WAWebhookPayload(BaseModel):
    object: str
    entry: list[WAWebhookEntry]


class WASendResult(BaseModel):
    message_id: str
    status: Literal["sent", "failed"]
    error: str | None = None
