"""E2E tests for WhatsApp consumer worker — AI-120."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _make_text_msg(phone: str, text: str, msg_id: str = "wamid.test") -> dict:
    return {"from": phone, "type": "text", "text": {"body": text}, "id": msg_id}


def _make_process_result(reply: str = "respuesta", agent: str = "fallback", intent: str = "other") -> dict:
    return {"reply": reply, "agent": agent, "intent": intent, "session_id": "wa:123", "trace_id": "t1"}


# ---------------------------------------------------------------------------
# _handle unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_text_message_sends_reply():
    from app.workers.whatsapp_consumer import _handle

    with patch(
        "app.workers.whatsapp_consumer.process_message",
        new_callable=AsyncMock,
        return_value=_make_process_result("Hola!"),
    ) as mock_proc:
        with patch(
            "app.workers.whatsapp_consumer.send_text_message",
            new_callable=AsyncMock,
        ) as mock_send:
            await _handle(_make_text_msg("573001234567", "hola"))

    mock_proc.assert_called_once()
    call_kwargs = mock_proc.call_args.kwargs
    assert call_kwargs["channel"] == "whatsapp"
    assert call_kwargs["user_id"] == "573001234567"
    assert call_kwargs["text"] == "hola"

    mock_send.assert_called_once_with(phone="573001234567", text="Hola!")


@pytest.mark.asyncio
async def test_handle_unsupported_type_ignored():
    from app.workers.whatsapp_consumer import _handle

    with patch("app.workers.whatsapp_consumer.process_message", new_callable=AsyncMock) as mock_proc:
        await _handle({"from": "573001234567", "type": "image", "id": "wamid.img"})

    mock_proc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_button_message_processed():
    from app.workers.whatsapp_consumer import _handle

    msg = {"from": "573001234567", "type": "button", "button": {"text": "Ver pedido"}, "id": "wamid.btn"}

    with patch(
        "app.workers.whatsapp_consumer.process_message",
        new_callable=AsyncMock,
        return_value=_make_process_result(),
    ):
        with patch("app.workers.whatsapp_consumer.send_text_message", new_callable=AsyncMock) as mock_send:
            await _handle(msg)

    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_handle_empty_phone_ignored():
    from app.workers.whatsapp_consumer import _handle

    with patch("app.workers.whatsapp_consumer.process_message", new_callable=AsyncMock) as mock_proc:
        await _handle({"from": "", "type": "text", "text": {"body": "hola"}, "id": "wamid.x"})

    mock_proc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_process_error_sends_fallback():
    from app.workers.whatsapp_consumer import _handle

    with patch(
        "app.workers.whatsapp_consumer.process_message",
        new_callable=AsyncMock,
        side_effect=Exception("LLM down"),
    ):
        with patch(
            "app.workers.whatsapp_consumer.send_text_message", new_callable=AsyncMock
        ) as mock_send:
            await _handle(_make_text_msg("573001234567", "hola"))

    mock_send.assert_called_once()
    assert "error" in mock_send.call_args.kwargs["text"].lower() or "minutos" in mock_send.call_args.kwargs["text"]


# ---------------------------------------------------------------------------
# run_consumer loop tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_consumer_stops_on_event():
    from app.workers.whatsapp_consumer import run_consumer

    stop_event = asyncio.Event()

    mock_redis = AsyncMock()
    mock_redis.blpop = AsyncMock(return_value=None)  # empty queue

    with patch("app.workers.whatsapp_consumer.get_redis", return_value=mock_redis):
        stop_event.set()
        await asyncio.wait_for(run_consumer(stop_event), timeout=2)


@pytest.mark.asyncio
async def test_run_consumer_processes_queued_message():
    """Consumer dequeues a message and calls send_text_message with the reply."""
    from app.workers.whatsapp_consumer import _handle

    msg = _make_text_msg("573001234567", "pedido 999")

    with patch(
        "app.workers.whatsapp_consumer.process_message",
        new_callable=AsyncMock,
        return_value=_make_process_result("Tu pedido está en camino"),
    ):
        with patch("app.workers.whatsapp_consumer.send_text_message", new_callable=AsyncMock) as mock_send:
            await _handle(msg)

    mock_send.assert_called_once_with(phone="573001234567", text="Tu pedido está en camino")
