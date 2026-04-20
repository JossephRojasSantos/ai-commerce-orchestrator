"""Tests for chat DB persistence via handle_message and get_or_create_conversation."""
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from sqlalchemy import select

from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatRequest
from app.services.chat import get_or_create_conversation, handle_message


SESSION_ID = uuid.UUID("123e4567-e89b-12d3-a456-426614174001")


def _make_request(msg: str = "Hola") -> ChatRequest:
    return ChatRequest(
        message=msg,
        session_id=SESSION_ID,
        timestamp=datetime(2026, 4, 8, 12, 0, 0, tzinfo=UTC),
    )


async def _fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_conversation_created_on_first_message(db_session):
    redis = await _fake_redis()
    req = _make_request()

    with patch("redis.asyncio.from_url", return_value=redis):
        await handle_message(req, redis, request_id="test-001", db=db_session)

    result = await db_session.execute(
        select(Conversation).where(Conversation.session_id == SESSION_ID)
    )
    conv = result.scalar_one_or_none()
    assert conv is not None

    await redis.aclose()


@pytest.mark.asyncio
async def test_messages_persisted_roundtrip(db_session):
    redis = await _fake_redis()
    req = _make_request("¿Tienen envío gratis?")

    with patch("redis.asyncio.from_url", return_value=redis):
        await handle_message(req, redis, request_id="test-002", db=db_session)

    result = await db_session.execute(
        select(Conversation).where(Conversation.session_id == SESSION_ID)
    )
    conv = result.scalar_one_or_none()
    assert conv is not None

    msgs_result = await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id)
    )
    messages = msgs_result.scalars().all()
    assert len(messages) == 2
    roles = {m.role for m in messages}
    assert roles == {"user", "assistant"}

    await redis.aclose()


@pytest.mark.asyncio
async def test_get_or_create_conversation_idempotent(db_session):
    conv1 = await get_or_create_conversation(SESSION_ID, db_session)
    conv2 = await get_or_create_conversation(SESSION_ID, db_session)
    assert conv1.id == conv2.id
