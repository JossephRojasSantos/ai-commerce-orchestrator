"""Tests de métricas IA y persistencia WS (T023)."""

from unittest.mock import patch

import pytest
from app.routers.ws import _persist_exchange


@pytest.mark.asyncio
async def test_persist_exchange_writes_pair(monkeypatch):
    added = []

    class FakeDB:
        def add(self, obj):
            added.append(obj)

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def execute(self, *_a, **_k):
            class R:
                def scalar_one_or_none(self):
                    return None

            return R()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("app.db.base.AsyncSessionLocal", return_value=FakeDB()):
        await _persist_exchange(
            "123e4567-e89b-12d3-a456-426614174000",
            "hola",
            "respuesta",
            "recommend",
            "recommendation",
        )

    # conversación + 2 mensajes
    assert len(added) == 3
    assistant = added[-1]
    assert assistant.role == "assistant"
    assert assistant.metadata_ == {"intent": "recommend", "agent": "recommendation"}


@pytest.mark.asyncio
async def test_persist_exchange_swallows_db_errors():
    with patch("app.db.base.AsyncSessionLocal", side_effect=RuntimeError("db down")):
        # no debe lanzar
        await _persist_exchange(
            "123e4567-e89b-12d3-a456-426614174000", "hola", "r", "other", "fallback"
        )


@pytest.mark.asyncio
async def test_ai_metrics_endpoint(admin_client):
    class FakeResult:
        def __init__(self, value):
            self._v = value

        def scalar(self):
            return self._v

        def all(self):
            return self._v

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, *_a, **_k):
            self.calls += 1
            if self.calls == 1:
                return FakeResult(2)  # conversations
            if self.calls == 2:
                return FakeResult(5)  # messages
            return FakeResult([({"intent": "recommend"},), ({"intent": "recommend"},), (None,)])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("app.db.base.AsyncSessionLocal", return_value=FakeDB()):
        resp = await admin_client.get("/v1/admin/ai/metrics", headers={"Authorization": "Bearer t"})

    data = resp.json()
    assert data["conversations"] == 2
    assert data["messages"] == 5
    assert data["intents"] == {"recommend": 2, "other": 1}
