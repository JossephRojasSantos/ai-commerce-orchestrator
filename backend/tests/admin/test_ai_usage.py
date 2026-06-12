"""Tests del registro y agregación de consumo IA (feature 013, T007)."""

from unittest.mock import AsyncMock, patch

import pytest
from app.services.admin.ai_usage import estimate_cost, record_usage


def test_estimate_cost_known_models():
    # gpt-4o-mini: 0.15 in / 0.60 out por millón
    cost = estimate_cost("openai/gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 0.60)
    # matching por prefijo (sufijos de OpenRouter)
    cost2 = estimate_cost("openai/gpt-4o-mini-2024-07-18", 2_000_000, 0)
    assert cost2 == pytest.approx(0.30)


def test_estimate_cost_unknown_model_returns_none():
    assert estimate_cost("desconocido/modelo-x", 1000, 1000) is None


@pytest.mark.asyncio
async def test_record_usage_swallows_db_errors():
    with patch("app.db.base.AsyncSessionLocal", side_effect=RuntimeError("db down")):
        # no debe lanzar (best-effort — jamás romper una respuesta del bot)
        await record_usage("openai/gpt-4o-mini", 100, 50)


@pytest.mark.asyncio
async def test_record_usage_persists(monkeypatch):
    added = []

    class FakeDB:
        def add(self, obj):
            added.append(obj)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("app.db.base.AsyncSessionLocal", return_value=FakeDB()):
        await record_usage("openai/gpt-4o-mini", 1000, 500, session_id="s1", channel="web")

    assert len(added) == 1
    rec = added[0]
    assert rec.prompt_tokens == 1000 and rec.completion_tokens == 500
    assert rec.cost_usd == pytest.approx(1000 / 1e6 * 0.15 + 500 / 1e6 * 0.60)
    assert rec.session_id == "s1" and rec.channel == "web"


@pytest.mark.asyncio
async def test_llm_client_schedules_usage_recording():
    """chat_complete registra usage sin cambiar su contrato (research R1)."""
    import httpx
    import respx
    from app.clients.llm import chat_complete
    from app.config import settings

    captured = {}

    async def fake_record(**kwargs):
        captured.update(kwargs)

    with (
        respx.mock,
        patch(
            "app.services.admin.ai_usage.record_usage",
            new=AsyncMock(side_effect=fake_record),
        ),
    ):
        respx.post(f"{settings.LLM_API_BASE}/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "openai/gpt-4o-mini",
                    "choices": [{"message": {"content": "hola"}}],
                    "usage": {"prompt_tokens": 42, "completion_tokens": 7},
                },
            )
        )
        reply = await chat_complete([{"role": "user", "content": "hi"}])
        # dar turno al create_task
        import asyncio

        await asyncio.sleep(0)

    assert reply == "hola"
    assert captured.get("prompt_tokens") == 42
    assert captured.get("completion_tokens") == 7
    assert captured.get("model") == "openai/gpt-4o-mini"
