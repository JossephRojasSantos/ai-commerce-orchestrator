from __future__ import annotations

import base64
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


def _sign(body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


async def _post(headers: dict, body: bytes) -> tuple[int, dict]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/webhooks/wc", content=body, headers=headers)
    return resp.status_code, (resp.json() if resp.content else {})


@pytest.mark.asyncio
async def test_webhook_product_created_ok(monkeypatch):
    secret = "test_secret"
    monkeypatch.setattr(settings, "WC_WEBHOOK_SECRET", secret)
    payload = {"id": 42, "name": "Test", "description": "", "short_description": ""}
    body = json.dumps(payload).encode()
    headers = {
        "X-WC-Webhook-Signature": _sign(body, secret),
        "X-WC-Webhook-Topic": "product.created",
        "Content-Type": "application/json",
    }
    with patch("app.routers.wc_webhook.index_product", new_callable=AsyncMock) as mock_index:
        status, data = await _post(headers, body)
    assert status == 200
    assert data == {"ok": True}
    mock_index.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_product_updated_ok(monkeypatch):
    secret = "test_secret"
    monkeypatch.setattr(settings, "WC_WEBHOOK_SECRET", secret)
    payload = {"id": 7, "name": "Upd"}
    body = json.dumps(payload).encode()
    headers = {
        "X-WC-Webhook-Signature": _sign(body, secret),
        "X-WC-Webhook-Topic": "product.updated",
        "Content-Type": "application/json",
    }
    with patch("app.routers.wc_webhook.index_product", new_callable=AsyncMock) as mock_index:
        status, data = await _post(headers, body)
    assert status == 200
    assert data == {"ok": True}
    mock_index.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_product_deleted_ok(monkeypatch):
    secret = "test_secret"
    monkeypatch.setattr(settings, "WC_WEBHOOK_SECRET", secret)
    payload = {"id": 99}
    body = json.dumps(payload).encode()
    headers = {
        "X-WC-Webhook-Signature": _sign(body, secret),
        "X-WC-Webhook-Topic": "product.deleted",
        "Content-Type": "application/json",
    }
    with patch("app.routers.wc_webhook.delete_product", new_callable=AsyncMock) as mock_delete:
        status, data = await _post(headers, body)
    assert status == 200
    assert data == {"ok": True}
    mock_delete.assert_called_once_with(99)


@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected(monkeypatch):
    secret = "test_secret"
    monkeypatch.setattr(settings, "WC_WEBHOOK_SECRET", secret)
    body = json.dumps({"id": 1}).encode()
    headers = {
        "X-WC-Webhook-Signature": "wrongsignaturebase64==",
        "X-WC-Webhook-Topic": "product.updated",
        "Content-Type": "application/json",
    }
    status, _ = await _post(headers, body)
    assert status == 401


@pytest.mark.asyncio
async def test_webhook_no_secret_skips_verification(monkeypatch):
    monkeypatch.setattr(settings, "WC_WEBHOOK_SECRET", "")
    body = json.dumps({"id": 5}).encode()
    headers = {
        "X-WC-Webhook-Topic": "product.created",
        "Content-Type": "application/json",
    }
    with patch("app.routers.wc_webhook.index_product", new_callable=AsyncMock) as mock_index:
        status, data = await _post(headers, body)
    assert status == 200
    assert data == {"ok": True}
    mock_index.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_unknown_topic_returns_200(monkeypatch):
    secret = "test_secret"
    monkeypatch.setattr(settings, "WC_WEBHOOK_SECRET", secret)
    body = json.dumps({"id": 1}).encode()
    headers = {
        "X-WC-Webhook-Signature": _sign(body, secret),
        "X-WC-Webhook-Topic": "order.created",
        "Content-Type": "application/json",
    }
    status, data = await _post(headers, body)
    assert status == 200
    assert data == {"ok": True}
