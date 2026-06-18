"""Tests de la bandeja WhatsApp: persistencia, modo humano, ventana 24h (T012)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from app.services import wa_inbox
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DDL = """
CREATE TABLE IF NOT EXISTS wa_conversations (
    id TEXT PRIMARY KEY,
    phone TEXT UNIQUE NOT NULL,
    name TEXT,
    mode TEXT DEFAULT 'bot',
    human_until DATETIME,
    last_customer_msg_at DATETIME,
    last_activity_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS wa_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES wa_conversations(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    content TEXT NOT NULL,
    delivered BOOLEAN DEFAULT 1,
    wa_message_id TEXT,
    status TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
async def wa_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for stmt in _DDL.strip().split(";"):
            if stmt.strip():
                await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    with patch("app.services.wa_inbox.AsyncSessionLocal", maker):
        yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_incoming_creates_conversation_and_returns_bot_reply(wa_db):
    should_reply = await wa_inbox.record_incoming("+57 316 623 5026", "hola", name="Josseph")
    assert should_reply is True

    items = await wa_inbox.list_conversations()
    assert len(items) == 1
    c = items[0]
    assert c["phone"] == "573166235026"
    assert c["name"] == "Josseph"
    assert c["mode"] == "bot"
    assert c["window_open"] is True
    assert c["last_message"] == "hola"


@pytest.mark.asyncio
async def test_thread_chronological_with_authors(wa_db):
    await wa_inbox.record_incoming("573001112233", "quiero info")
    await wa_inbox.record_outgoing("573001112233", "claro, dime", author="bot")
    await wa_inbox.record_outgoing("573001112233", "soy el admin", author="admin")

    thread = await wa_inbox.get_thread("573001112233")
    authors = [m["author"] for m in thread["messages"]]
    assert authors == ["customer", "bot", "admin"]


@pytest.mark.asyncio
async def test_non_text_placeholder(wa_db):
    await wa_inbox.record_incoming("573001112233", "")
    thread = await wa_inbox.get_thread("573001112233")
    assert thread["messages"][0]["content"] == wa_inbox.NON_TEXT_PLACEHOLDER


@pytest.mark.asyncio
async def test_human_mode_blocks_bot_and_expires(wa_db):
    await wa_inbox.record_incoming("573009998877", "hola")
    await wa_inbox.set_mode("573009998877", "human")

    # vigente → el bot no responde
    assert await wa_inbox.record_incoming("573009998877", "sigues ahí?") is False

    # expirar la pausa manualmente
    async with wa_db() as db:
        await db.execute(
            text("UPDATE wa_conversations SET human_until = :t"),
            {"t": datetime.now(UTC) - timedelta(minutes=1)},
        )
        await db.commit()

    # expirada → vuelve al bot
    assert await wa_inbox.record_incoming("573009998877", "hola de nuevo") is True
    thread = await wa_inbox.get_thread("573009998877")
    assert thread["mode"] == "bot"


@pytest.mark.asyncio
async def test_outgoing_stores_wa_message_id_and_status(wa_db):
    await wa_inbox.record_outgoing(
        "573001112233", "respuesta", author="bot", wa_message_id="wamid.abc"
    )
    thread = await wa_inbox.get_thread("573001112233")
    assert thread["messages"][0]["status"] == "sent"


@pytest.mark.asyncio
async def test_update_message_status_by_wa_id(wa_db):
    await wa_inbox.record_outgoing(
        "573001112233", "respuesta", author="bot", wa_message_id="wamid.abc"
    )
    assert await wa_inbox.update_message_status("wamid.abc", "read") is True
    thread = await wa_inbox.get_thread("573001112233")
    assert thread["messages"][0]["status"] == "read"
    assert thread["messages"][0]["delivered"] is True

    # failed marca delivered=False
    assert await wa_inbox.update_message_status("wamid.abc", "failed") is True
    thread = await wa_inbox.get_thread("573001112233")
    assert thread["messages"][0]["delivered"] is False

    # id desconocido → False, sin error
    assert await wa_inbox.update_message_status("wamid.nope", "delivered") is False


@pytest.mark.asyncio
async def test_window_closed_when_old_message(wa_db):
    await wa_inbox.record_incoming("573005554433", "viejo")
    async with wa_db() as db:
        await db.execute(
            text("UPDATE wa_conversations SET last_customer_msg_at = :t"),
            {"t": datetime.now(UTC) - timedelta(hours=25)},
        )
        await db.commit()
    thread = await wa_inbox.get_thread("573005554433")
    assert thread["window_open"] is False
