"""Bandeja de WhatsApp: persistencia, modo humano y ventana de 24h (feature 013).

Reglas (research R3-R5):
- Conversación por teléfono normalizado; mensajes con autor customer|bot|admin.
- mode=human pausa el bot; expira perezosamente (human_until).
- window_open: último mensaje del cliente hace < 24h (regla de Meta).
"""

import re
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import desc, select

from app.config import settings
from app.db.base import AsyncSessionLocal
from app.models.wa_conversation import WaConversation, WaMessage

logger = structlog.get_logger()

NON_TEXT_PLACEHOLDER = "[mensaje no de texto]"
_WINDOW = timedelta(hours=24)


def normalize_phone(raw: str) -> str:
    return re.sub(r"\D+", "", raw or "")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def window_open(conv: WaConversation) -> bool:
    last = _aware(conv.last_customer_msg_at)
    return last is not None and (_now() - last) < _WINDOW


def human_mode_active(conv: WaConversation) -> bool:
    if conv.mode != "human":
        return False
    until = _aware(conv.human_until)
    return until is not None and _now() < until


async def record_incoming(phone: str, content: str, name: str | None = None) -> bool:
    """Persiste un mensaje del cliente. Devuelve True si el BOT debe responder.

    Evalúa la expiración perezosa del modo humano (research R5).
    """
    phone = normalize_phone(phone)
    now = _now()
    async with AsyncSessionLocal() as db:
        conv = (
            await db.execute(select(WaConversation).where(WaConversation.phone == phone))
        ).scalar_one_or_none()
        if conv is None:
            conv = WaConversation(phone=phone, name=name, mode="bot")
            db.add(conv)
            await db.flush()
        elif name and not conv.name:
            conv.name = name

        bot_should_reply = True
        if human_mode_active(conv):
            bot_should_reply = False
        elif conv.mode == "human":
            # pausa expirada → vuelve al bot
            conv.mode = "bot"
            conv.human_until = None

        conv.last_customer_msg_at = now
        conv.last_activity_at = now
        db.add(
            WaMessage(
                conversation_id=conv.id, author="customer", content=content or NON_TEXT_PLACEHOLDER
            )
        )
        await db.commit()
    return bot_should_reply


async def record_outgoing(phone: str, content: str, author: str, delivered: bool = True) -> None:
    """Persiste un mensaje saliente (bot o admin). Best-effort para el flujo del bot."""
    phone = normalize_phone(phone)
    now = _now()
    async with AsyncSessionLocal() as db:
        conv = (
            await db.execute(select(WaConversation).where(WaConversation.phone == phone))
        ).scalar_one_or_none()
        if conv is None:
            conv = WaConversation(phone=phone, mode="bot")
            db.add(conv)
            await db.flush()
        conv.last_activity_at = now
        db.add(
            WaMessage(conversation_id=conv.id, author=author, content=content, delivered=delivered)
        )
        await db.commit()


async def set_mode(phone: str, mode: str) -> WaConversation | None:
    phone = normalize_phone(phone)
    async with AsyncSessionLocal() as db:
        conv = (
            await db.execute(select(WaConversation).where(WaConversation.phone == phone))
        ).scalar_one_or_none()
        if conv is None:
            return None
        conv.mode = mode
        conv.human_until = (
            _now() + timedelta(hours=settings.WA_HUMAN_PAUSE_HOURS) if mode == "human" else None
        )
        await db.commit()
        await db.refresh(conv)
    return conv


def _conv_dto(conv: WaConversation, last_msg: WaMessage | None = None) -> dict:
    return {
        "phone": conv.phone,
        "name": conv.name,
        "mode": "human" if human_mode_active(conv) else "bot",
        "last_message": (last_msg.content[:120] if last_msg else ""),
        "last_author": (last_msg.author if last_msg else ""),
        "last_activity": conv.last_activity_at.isoformat() if conv.last_activity_at else "",
        "window_open": window_open(conv),
        "human_until": conv.human_until.isoformat() if conv.human_until else None,
    }


async def list_conversations(limit: int = 50) -> list[dict]:
    async with AsyncSessionLocal() as db:
        convs = (
            (
                await db.execute(
                    select(WaConversation)
                    .order_by(desc(WaConversation.last_activity_at))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        items = []
        for c in convs:
            last = (
                await db.execute(
                    select(WaMessage)
                    .where(WaMessage.conversation_id == c.id)
                    .order_by(desc(WaMessage.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            items.append(_conv_dto(c, last))
    return items


async def get_thread(phone: str) -> dict | None:
    phone = normalize_phone(phone)
    async with AsyncSessionLocal() as db:
        conv = (
            await db.execute(select(WaConversation).where(WaConversation.phone == phone))
        ).scalar_one_or_none()
        if conv is None:
            return None
        msgs = (
            (
                await db.execute(
                    select(WaMessage)
                    .where(WaMessage.conversation_id == conv.id)
                    .order_by(WaMessage.created_at)
                )
            )
            .scalars()
            .all()
        )
    dto = _conv_dto(conv, msgs[-1] if msgs else None)
    dto["messages"] = [
        {
            "author": m.author,
            "content": m.content,
            "date": m.created_at.isoformat() if m.created_at else "",
            "delivered": m.delivered,
        }
        for m in msgs
    ]
    return dto
