"""Tests de envío y visualización de adjuntos en el inbox admin."""

from unittest.mock import AsyncMock, patch

import pytest
from app.integrations.whatsapp.models import WASendResult


def _thread(window_open=True):
    return {"phone": "573166235026", "window_open": window_open, "mode": "bot", "messages": []}


class _Conv:
    human_until = None


_URL = "/v1/admin/wa/conversations/573166235026/reply-media"
_AUTH = {"Authorization": "Bearer t"}


@pytest.mark.asyncio
async def test_reply_media_image_ok(admin_client):
    sent = WASendResult(message_id="wamid.m", status="sent")
    with (
        patch("app.services.wa_inbox.get_thread", new_callable=AsyncMock, return_value=_thread()),
        patch("app.services.wa_inbox.record_outgoing", new_callable=AsyncMock) as mock_rec,
        patch("app.services.wa_inbox.set_mode", new_callable=AsyncMock, return_value=_Conv()),
        patch(
            "app.integrations.whatsapp.client.upload_media",
            new_callable=AsyncMock,
            return_value="MID-1",
        ) as mock_up,
        patch(
            "app.integrations.whatsapp.client.send_media_message",
            new_callable=AsyncMock,
            return_value=sent,
        ) as mock_send,
    ):
        resp = await admin_client.post(
            _URL,
            files={"file": ("foto.png", b"\x89PNG\r\n", "image/png")},
            data={"caption": "mira esto"},
            headers=_AUTH,
        )

    assert resp.status_code == 200
    assert resp.json()["mode"] == "human"
    mock_up.assert_awaited_once()
    assert mock_send.await_args.kwargs["media_type"] == "image"
    assert mock_rec.await_args.kwargs["media_id"] == "MID-1"
    assert mock_rec.await_args.kwargs["author"] == "admin"


@pytest.mark.asyncio
async def test_reply_media_unsupported_type_415(admin_client):
    resp = await admin_client.post(
        _URL,
        files={"file": ("video.mp4", b"\x00\x00", "video/mp4")},
        headers=_AUTH,
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_reply_media_window_closed_409(admin_client):
    with patch(
        "app.services.wa_inbox.get_thread",
        new_callable=AsyncMock,
        return_value=_thread(window_open=False),
    ):
        resp = await admin_client.post(
            _URL,
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
            headers=_AUTH,
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_reply_media_upload_failed_502(admin_client):
    with (
        patch("app.services.wa_inbox.get_thread", new_callable=AsyncMock, return_value=_thread()),
        patch(
            "app.integrations.whatsapp.client.upload_media",
            new_callable=AsyncMock,
            return_value="",
        ),
    ):
        resp = await admin_client.post(
            _URL,
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
            headers=_AUTH,
        )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_media_proxy_ok(admin_client):
    with patch(
        "app.integrations.whatsapp.media.download_media",
        new_callable=AsyncMock,
        return_value=(b"BYTES", "image/png"),
    ):
        resp = await admin_client.get("/v1/admin/wa/media/MID-1", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.content == b"BYTES"
    assert resp.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_media_proxy_not_found_404(admin_client):
    with patch(
        "app.integrations.whatsapp.media.download_media",
        new_callable=AsyncMock,
        return_value=(b"", ""),
    ):
        resp = await admin_client.get("/v1/admin/wa/media/MISSING", headers=_AUTH)
    assert resp.status_code == 404
