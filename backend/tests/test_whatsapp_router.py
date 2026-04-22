"""Coverage for app/routers/whatsapp.py — webhook verify + receive."""
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_SECRET = "test_app_secret"
_VERIFY_TOKEN = "test_verify_token"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _patch_settings():
    mock_cfg = MagicMock()
    mock_cfg.WA_APP_SECRET = _SECRET
    mock_cfg.WA_WEBHOOK_VERIFY_TOKEN = _VERIFY_TOKEN
    mock_cfg.WA_RATE_LIMIT_PER_HOUR = 10
    return patch("app.routers.whatsapp.settings", mock_cfg)


@pytest.fixture
async def wa_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_webhook_verify_ok(wa_client):
    with _patch_settings():
        resp = await wa_client.get(
            "/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "challenge_string",
                "hub.verify_token": _VERIFY_TOKEN,
            },
        )
    assert resp.status_code == 200
    assert resp.text == "challenge_string"


@pytest.mark.asyncio
async def test_webhook_verify_wrong_token(wa_client):
    with _patch_settings():
        resp = await wa_client.get(
            "/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "challenge_string",
                "hub.verify_token": "wrong_token",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_receive_invalid_signature(wa_client):
    body = json.dumps({"entry": []}).encode()
    with _patch_settings():
        resp = await wa_client.post(
            "/api/whatsapp/webhook",
            content=body,
            headers={"X-Hub-Signature-256": "sha256=invalid", "Content-Type": "application/json"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_receive_no_signature(wa_client):
    body = json.dumps({"entry": []}).encode()
    with _patch_settings():
        resp = await wa_client.post(
            "/api/whatsapp/webhook",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_receive_valid_empty_payload(wa_client):
    payload = {"entry": []}
    body = json.dumps(payload).encode()
    sig = _sign(body)

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.rpush = AsyncMock()

    with _patch_settings():
        with patch("app.core.cache.get_redis", return_value=mock_redis):
            resp = await wa_client.post(
                "/api/whatsapp/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}


@pytest.mark.asyncio
async def test_webhook_receive_enqueues_message(wa_client):
    message_id = "wamid.test001"
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [{"id": message_id, "type": "text", "text": {"body": "hola"}}]
                        },
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    sig = _sign(body)

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.rpush = AsyncMock()

    with _patch_settings():
        with patch("app.routers.whatsapp.get_redis", return_value=mock_redis):
            resp = await wa_client.post(
                "/api/whatsapp/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
            )
    assert resp.status_code == 200
    mock_redis.rpush.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_receive_duplicate_message_skipped(wa_client):
    message_id = "wamid.duplicate"
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {"messages": [{"id": message_id, "type": "text"}]},
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    sig = _sign(body)

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.set = AsyncMock(return_value=None)
    mock_redis.rpush = AsyncMock()

    with _patch_settings():
        with patch("app.routers.whatsapp.get_redis", return_value=mock_redis):
            resp = await wa_client.post(
                "/api/whatsapp/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
            )
    assert resp.status_code == 200
    mock_redis.rpush.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_receive_non_messages_field_ignored(wa_client):
    payload = {
        "entry": [
            {
                "changes": [
                    {"field": "statuses", "value": {}}
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    sig = _sign(body)

    mock_redis = AsyncMock()

    with _patch_settings():
        with patch("app.routers.whatsapp.get_redis", return_value=mock_redis):
            resp = await wa_client.post(
                "/api/whatsapp/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
            )
    assert resp.status_code == 200
    mock_redis.rpush.assert_not_called()
