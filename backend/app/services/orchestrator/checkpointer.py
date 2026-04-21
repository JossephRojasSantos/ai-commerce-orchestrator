from langgraph.checkpoint.memory import MemorySaver

from app.config import settings


def get_checkpointer():
    """Return a checkpointer. Uses AsyncRedisSaver when Redis URL is configured."""
    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver
        return AsyncRedisSaver.from_conn_string(settings.REDIS_URL)
    except Exception:
        return MemorySaver()
