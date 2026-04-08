import orjson
import redis.asyncio as aioredis
import structlog

from app.config import settings

logger = structlog.get_logger()

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis


async def cache_get(key: str) -> dict | list | None:
    r = get_redis()
    val = await r.get(key)
    if val is None:
        logger.debug("cache MISS", key=key)
        return None
    logger.debug("cache HIT", key=key)
    return orjson.loads(val)


async def cache_set(key: str, value: dict | list, ttl: int) -> None:
    r = get_redis()
    await r.set(key, orjson.dumps(value), ex=ttl)
