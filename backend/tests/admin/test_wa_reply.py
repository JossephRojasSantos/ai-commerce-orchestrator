"""Tests de respuesta manual por WhatsApp (feature 013, T016)."""

from unittest.mock import AsyncMock, patch

import pytest
from app.integrations.whatsapp.models import WASendResult


def _thread(window_open=True):
    return {
        "phone": "573166235026",
        "window_open": window_open,
        "mode": "bot",
        "messages": [],
    }


class _Conv:
    human_until = None


@pytest.mark.asyncio
async def test_reply_ok_sets_human_mode(admin_client):
    sent = WASendResult(message_id="wamid.x", status="sent")
    with (
        patch("app.services.wa_inbox.get_thread", new_callable=AsyncMock, return_value=_thread()),
        patch("app.services.wa_inbox.record_outgoing", new_callable=AsyncMock) as mock_rec,
        patch("app.services.wa_inbox.set_mode", new_callable=AsyncMock, return_value=_Conv()),
        patch(
            "app.integrations.whatsapp.client.send_text_message",
            new_callable=AsyncMock,
            return_value=sent,
        ) as mock_send,
    ):
        resp = await admin_client.post(
            "/v1/admin/wa/conversations/573166235026/reply",
            json={"text": "hola, soy el admin"},
            headers={"Authorization": "Bearer t"},
        )

    assert resp.status_code == 200
    assert resp.json()["mode"] == "human"
    mock_send.assert_awaited_once()
    mock_rec.assert_awaited_once()
    assert mock_rec.await_args.kwargs.get("author") == "admin"


@pytest.mark.asyncio
async def test_reply_window_closed_409(admin_client):
    with patch(
        "app.services.wa_inbox.get_thread",
        new_callable=AsyncMock,
        return_value=_thread(window_open=False),
    ):
        resp = await admin_client.post(
            "/v1/admin/wa/conversations/573166235026/reply",
            json={"text": "tarde"},
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 409
    body = resp.json()
    assert body.get("detail") == "window_closed" or body.get("message") == "window_closed"


@pytest.mark.asyncio
async def test_reply_meta_failure_502_and_delivered_false(admin_client):
    fail = WASendResult(message_id="", status="failed", error="boom")
    with (
        patch("app.services.wa_inbox.get_thread", new_callable=AsyncMock, return_value=_thread()),
        patch("app.services.wa_inbox.record_outgoing", new_callable=AsyncMock) as mock_rec,
        patch(
            "app.integrations.whatsapp.client.send_text_message",
            new_callable=AsyncMock,
            return_value=fail,
        ),
    ):
        resp = await admin_client.post(
            "/v1/admin/wa/conversations/573166235026/reply",
            json={"text": "no llega"},
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 502
    assert mock_rec.await_args.kwargs.get("delivered") is False


@pytest.mark.asyncio
async def test_reply_404_and_resume_bot(admin_client):
    with patch("app.services.wa_inbox.get_thread", new_callable=AsyncMock, return_value=None):
        nf = await admin_client.post(
            "/v1/admin/wa/conversations/000/reply",
            json={"text": "x"},
            headers={"Authorization": "Bearer t"},
        )
    assert nf.status_code == 404

    with patch("app.services.wa_inbox.set_mode", new_callable=AsyncMock, return_value=_Conv()):
        ok = await admin_client.post(
            "/v1/admin/wa/conversations/573166235026/resume-bot",
            headers={"Authorization": "Bearer t"},
        )
    assert ok.status_code == 200 and ok.json()["mode"] == "bot"
