from unittest.mock import patch

import fakeredis.aioredis
import pytest
from app.core import cache as cache_module


@pytest.mark.asyncio
async def test_cache_set_get_roundtrip():
    fake = fakeredis.aioredis.FakeRedis()
    with patch.object(cache_module, "get_redis", return_value=fake):
        await cache_module.cache_set("test:key", {"foo": "bar"}, ttl=60)
        result = await cache_module.cache_get("test:key")
    assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_cache_miss_returns_none():
    fake = fakeredis.aioredis.FakeRedis()
    with patch.object(cache_module, "get_redis", return_value=fake):
        result = await cache_module.cache_get("nonexistent:key")
    assert result is None
