"""Coverage for app/routers/orchestrator.py"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient

_API_KEY = "key-web-test"
_AUTH = {"Authorization": f"Bearer {_API_KEY}"}


def _mock_redis(count: int = 1):
    r = AsyncMock()
    r.incr = AsyncMock(return_value=count)
    r.expire = AsyncMock()
    return r


def _patch_auth():
    return patch("app.core.auth.settings", MagicMock(ALLOWED_API_KEYS=[_API_KEY]))


@pytest.mark.asyncio
async def test_orchestrate_message_ok():
    mock_result = {
        "reply": "Aquí están las opciones.",
        "intent": "buy",
        "agent": "chat",
        "session_id": "web:user1",
        "trace_id": "trace-test",
    }
    with _patch_auth():
        with patch("app.routers.orchestrator.get_redis", return_value=_mock_redis(1)):
            with patch(
                "app.routers.orchestrator.process_message",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/orchestrator/message",
                        json={
                            "channel": "web",
                            "user_id": "user1",
                            "text": "quiero comprar zapatos",
                        },
                        headers=_AUTH,
                    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "buy"
    assert body["agent"] == "chat"
    assert "reply" in body


@pytest.mark.asyncio
async def test_orchestrate_message_no_api_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/orchestrator/message",
            json={"channel": "web", "user_id": "user1", "text": "hola"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_orchestrate_message_invalid_api_key():
    with _patch_auth():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/orchestrator/message",
                json={"channel": "web", "user_id": "user1", "text": "hola"},
                headers={"Authorization": "Bearer wrong-key"},
            )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_orchestrate_message_whatsapp_channel():
    mock_result = {
        "reply": "Hola!",
        "intent": "other",
        "agent": "fallback",
        "session_id": "whatsapp:5200",
        "trace_id": "t2",
    }
    with _patch_auth():
        with patch("app.routers.orchestrator.get_redis", return_value=_mock_redis(1)):
            with patch(
                "app.routers.orchestrator.process_message",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/v1/orchestrator/message",
                        json={"channel": "whatsapp", "user_id": "5200", "text": "hola"},
                        headers=_AUTH,
                    )
    assert resp.status_code == 200
    assert resp.json()["agent"] == "fallback"


@pytest.mark.asyncio
async def test_orchestrate_message_rate_limited():
    from app.config import settings

    with _patch_auth():
        with patch(
            "app.routers.orchestrator.get_redis",
            return_value=_mock_redis(settings.ORCHESTRATOR_RATE_LIMIT_PER_MIN + 1),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/orchestrator/message",
                    json={"channel": "web", "user_id": "abuser", "text": "spam"},
                    headers=_AUTH,
                )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_orchestrate_message_ip_rate_limited(_mock_middleware_redis):
    _mock_middleware_redis.incr = AsyncMock(return_value=9999)
    with _patch_auth(), patch("app.middleware.settings", MagicMock(IP_RATE_LIMIT_PER_MIN=10)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/orchestrator/message",
                json={"channel": "web", "user_id": "user1", "text": "spam"},
                headers=_AUTH,
            )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_orchestrate_message_validation_error():
    with _patch_auth():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/orchestrator/message",
                json={"channel": "web"},
                headers=_AUTH,
            )
    assert resp.status_code == 422
