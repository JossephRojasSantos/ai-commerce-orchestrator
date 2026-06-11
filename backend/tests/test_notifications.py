"""Tests del endpoint /v1/notifications/cod-order (feature 011)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.integrations.whatsapp.models import WASendResult
from app.main import app
from httpx import ASGITransport, AsyncClient

_API_KEY = "key-notif-test"
_AUTH = {"Authorization": f"Bearer {_API_KEY}"}


def _patch_auth():
    return patch("app.core.auth.settings", MagicMock(ALLOWED_API_KEYS=[_API_KEY]))


def _payload(**over):
    base = {
        "phone": "3001234567",
        "order_number": "95",
        "total": "$29.900",
        "customer_name": "Maria Paula",
    }
    base.update(over)
    return base


async def _post(payload, headers=_AUTH):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/notifications/cod-order", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_template_sent_ok():
    ok = WASendResult(message_id="wamid.1", status="sent")
    with (
        _patch_auth(),
        patch(
            "app.routers.notifications.send_template_message",
            new_callable=AsyncMock,
            return_value=ok,
        ) as mock_tpl,
    ):
        resp = await _post(_payload())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert data["fallback_used"] is False
    # E.164 sin '+': 57 + 10 dígitos
    assert mock_tpl.await_args.args[0] == "573001234567"
    assert mock_tpl.await_args.args[1] == "tm_confirmacion"


@pytest.mark.asyncio
async def test_fallback_text_when_template_fails():
    fail = WASendResult(message_id="", status="failed", error="template not approved")
    ok = WASendResult(message_id="wamid.2", status="sent")
    with (
        _patch_auth(),
        patch(
            "app.routers.notifications.send_template_message",
            new_callable=AsyncMock,
            return_value=fail,
        ),
        patch(
            "app.routers.notifications.send_text_message",
            new_callable=AsyncMock,
            return_value=ok,
        ) as mock_text,
    ):
        resp = await _post(_payload())

    data = resp.json()
    assert data["status"] == "sent"
    assert data["fallback_used"] is True
    assert "#95" in mock_text.await_args.args[1]
    assert "Maria" in mock_text.await_args.args[1]


@pytest.mark.asyncio
async def test_phone_normalization_and_rejection():
    ok = WASendResult(message_id="wamid.3", status="sent")
    with (
        _patch_auth(),
        patch(
            "app.routers.notifications.send_template_message",
            new_callable=AsyncMock,
            return_value=ok,
        ) as mock_tpl,
    ):
        resp = await _post(_payload(phone="+57 316 623 5026"))
        assert resp.status_code == 200
        assert mock_tpl.await_args.args[0] == "573166235026"

        bad = await _post(_payload(phone="12345"))
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_requires_api_key():
    with _patch_auth():
        resp = await _post(_payload(), headers={})
    assert resp.status_code in (401, 422)
