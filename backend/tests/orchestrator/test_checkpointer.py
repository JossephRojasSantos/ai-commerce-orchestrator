"""Unit tests for checkpointer — MemorySaver (AsyncRedisSaver requires async lifespan)."""
from app.services.orchestrator.checkpointer import get_checkpointer
from langgraph.checkpoint.memory import MemorySaver


def test_get_checkpointer_returns_memory_saver():
    result = get_checkpointer()
    assert isinstance(result, MemorySaver)


def test_get_checkpointer_returns_new_instance_each_call():
    a = get_checkpointer()
    b = get_checkpointer()
    assert isinstance(a, MemorySaver)
    assert isinstance(b, MemorySaver)
