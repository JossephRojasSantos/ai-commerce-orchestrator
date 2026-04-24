from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from app.main import app
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Raw DDL for SQLite — mirrors conversation.py models without PG-specific types
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_ip TEXT,
    user_agent TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS ix_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages(conversation_id);
"""


async def _make_sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        for stmt in _CREATE_TABLES_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))
    return engine


@pytest.fixture(autouse=True)
def _mock_middleware_redis():
    """Prevent IPRateLimitMiddleware from hitting real Redis in tests."""
    mock_r = AsyncMock()
    mock_r.incr = AsyncMock(return_value=1)
    mock_r.expire = AsyncMock()
    with patch("app.middleware.get_redis", return_value=mock_r):
        yield mock_r
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Raw DDL for SQLite — mirrors conversation.py models without PG-specific types
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_ip TEXT,
    user_agent TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS ix_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages(conversation_id);
"""


async def _make_sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        for stmt in _CREATE_TABLES_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))
    return engine


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_db_ok():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.close = AsyncMock()
    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=conn) as m:
        yield m


@pytest.fixture
def mock_redis_ok():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    redis_cls = MagicMock()
    redis_cls.from_url.return_value = r
    with patch("redis.asyncio.Redis", redis_cls) as m:
        yield m


@pytest.fixture
def mock_db_fail():
    with patch("asyncpg.connect", new_callable=AsyncMock, side_effect=Exception("DB down")) as m:
        yield m


@pytest.fixture
def mock_redis_fail():
    redis_cls = MagicMock()
    redis_cls.from_url.side_effect = Exception("Redis down")
    with patch("redis.asyncio.Redis", redis_cls) as m:
        yield m


# ---------------------------------------------------------------------------
# Chat test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def fake_redis():
    """FakeRedis instance that replaces redis.asyncio.from_url."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("redis.asyncio.from_url", return_value=redis):
        yield redis
    await redis.aclose()


@pytest.fixture
async def db_session():
    """SQLite in-memory async session with chat tables created via raw DDL."""
    engine = await _make_sqlite_engine()
    AsyncTestSession = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with AsyncTestSession() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def app_client(fake_redis):
    """Async HTTP client wired to the FastAPI app with SQLite DB override."""
    from app.db.base import get_db

    engine = await _make_sqlite_engine()
    AsyncTestSession = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with AsyncTestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()
