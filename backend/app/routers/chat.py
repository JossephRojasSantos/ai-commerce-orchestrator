from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_db
from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.services.chat import handle_message

router = APIRouter(prefix="/chat", tags=["chat"])


async def get_redis():
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@router.post("", response_model=ChatResponse)
async def post_chat(
    req: ChatRequest,
    request: Request,
    redis=Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", "")
    user_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await handle_message(req, redis, request_id, db=db, user_ip=user_ip, user_agent=user_agent)


@router.get("/history/{session_id}", response_model=list[ChatMessage])
async def get_history(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessage]:
    result = await db.execute(
        select(Conversation).where(Conversation.session_id == session_id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        return []

    msgs_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .limit(settings.CHAT_MAX_HISTORY)
    )
    messages = msgs_result.scalars().all()

    return [
        ChatMessage(role=m.role, content=m.content, timestamp=m.created_at)
        for m in messages
    ]
