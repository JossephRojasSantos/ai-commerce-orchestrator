import time
import uuid
from datetime import datetime

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse

logger = structlog.get_logger()


async def get_or_create_conversation(
    session_id: uuid.UUID,
    db: AsyncSession,
    user_ip: str | None = None,
    user_agent: str | None = None,
) -> Conversation:
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if conv is None:
        conv = Conversation(
            session_id=session_id,
            user_ip=user_ip,
            user_agent=user_agent,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
    return conv


async def save_message(
    conv_id: uuid.UUID,
    role: str,
    content: str,
    db: AsyncSession,
) -> Message:
    msg = Message(conversation_id=conv_id, role=role, content=content)
    db.add(msg)
    return msg


async def handle_message(
    req: ChatRequest,
    redis,
    request_id: str,
    db: AsyncSession | None = None,
    user_ip: str | None = None,
    user_agent: str | None = None,
) -> ChatResponse:
    start = time.monotonic()

    rate_key = f"ratelimit:chat:{req.session_id}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 60)

    if count > settings.CHAT_RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")

    reply = f"[Stub AI-26] Recibí: {req.message}"

    if db is not None:
        conv = await get_or_create_conversation(req.session_id, db, user_ip, user_agent)
        user_msg = await save_message(conv.id, "user", req.message, db)
        assistant_msg = await save_message(conv.id, "assistant", reply, db)
        await db.commit()
        await db.refresh(user_msg)
        await db.refresh(assistant_msg)

    messages = [
        ChatMessage(role="user", content=req.message, timestamp=req.timestamp),
        ChatMessage(role="assistant", content=reply, timestamp=datetime.utcnow()),
    ]

    latency_ms = round((time.monotonic() - start) * 1000, 2)
    logger.info(
        "chat_message_handled",
        session_id=str(req.session_id),
        request_id=request_id,
        latency_ms=latency_ms,
    )

    return ChatResponse(
        session_id=req.session_id,
        reply=reply,
        messages=messages,
        request_id=request_id,
    )
