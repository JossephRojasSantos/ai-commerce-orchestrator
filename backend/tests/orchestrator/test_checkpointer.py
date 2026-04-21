"""Unit tests for checkpointer — covers AsyncRedisSaver path and MemorySaver fallback."""
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from app.services.orchestrator.checkpointer import get_checkpointer


def test_get_checkpointer_redis_succeeds():
    """Covers lines 8-10: AsyncRedisSaver.from_conn_string returns a saver."""
    mock_saver = MagicMock()
    with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver.from_conn_string", return_value=mock_saver):
        result = get_checkpointer()
    assert result is mock_saver


def test_get_checkpointer_fallback_to_memory():
    """Covers lines 11-12: from_conn_string raises → MemorySaver returned."""
    with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver.from_conn_string", side_effect=Exception("Redis down")):
        result = get_checkpointer()
    assert isinstance(result, MemorySaver)
