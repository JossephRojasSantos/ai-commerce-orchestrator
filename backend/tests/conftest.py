from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


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
