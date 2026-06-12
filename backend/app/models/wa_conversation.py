"""Conversaciones y mensajes de WhatsApp con clientes (feature 013)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WaConversation(Base):
    __tablename__ = "wa_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mode: Mapped[str] = mapped_column(String(10), default="bot")  # bot | human
    human_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_customer_msg_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    messages: Mapped[list["WaMessage"]] = relationship(
        "WaMessage", back_populates="conversation", order_by="WaMessage.created_at"
    )


class WaMessage(Base):
    __tablename__ = "wa_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wa_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author: Mapped[str] = mapped_column(String(10), nullable=False)  # customer | bot | admin
    content: Mapped[str] = mapped_column(Text, nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )

    conversation: Mapped["WaConversation"] = relationship(
        "WaConversation", back_populates="messages"
    )
