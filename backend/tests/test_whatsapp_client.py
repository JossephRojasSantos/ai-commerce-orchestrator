"""Coverage for app/integrations/whatsapp/client.py"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.whatsapp.client import send_template_message, send_text_message, send_whatsapp_message


def _mock_resp(status: int, body: dict | None = None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    r.text = str(body)
    return r


def _make_client_ctx(resp):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=resp)
    return mock_client


@pytest.mark.asyncio
async def test_send_text_message_success():
    resp = _mock_resp(200, {"messages": [{"id": "msg-001"}]})
    with patch("app.integrations.whatsapp.client.httpx.AsyncClient", return_value=_make_client_ctx(resp)):
        result = await send_text_message("521234567890", "Hola!")
    assert result.status == "sent"
    assert result.message_id == "msg-001"


@pytest.mark.asyncio
async def test_send_template_message_success():
    resp = _mock_resp(200, {"messages": [{"id": "msg-002"}]})
    with patch("app.integrations.whatsapp.client.httpx.AsyncClient", return_value=_make_client_ctx(resp)):
        result = await send_template_message("521234567890", "order_confirm", {"name": "Juan"})
    assert result.status == "sent"
    assert result.message_id == "msg-002"


@pytest.mark.asyncio
async def test_send_text_message_non_retryable_error():
    resp = _mock_resp(400, {"error": "bad request"})
    with patch("app.integrations.whatsapp.client.httpx.AsyncClient", return_value=_make_client_ctx(resp)):
        result = await send_text_message("521234567890", "test")
    assert result.status == "failed"
    assert "400" in result.error


@pytest.mark.asyncio
async def test_send_text_message_request_error():
    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("timeout"))

    with patch("app.integrations.whatsapp.client.httpx.AsyncClient", return_value=mock_client):
        result = await send_text_message("521234567890", "test")
    assert result.status == "failed"
    assert result.error == "timeout"


@pytest.mark.asyncio
async def test_send_text_message_retryable_then_success():
    retry_resp = _mock_resp(429, {})
    ok_resp = _mock_resp(200, {"messages": [{"id": "msg-retry"}]})

    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return retry_resp if call_count == 1 else ok_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=mock_post)

    with patch("app.integrations.whatsapp.client.httpx.AsyncClient", return_value=mock_client):
        with patch("app.integrations.whatsapp.client.asyncio.sleep", new_callable=AsyncMock):
            result = await send_text_message("521234567890", "test")

    assert result.status == "sent"
    assert call_count == 2
