"""Tests para el consumidor de status callbacks (Fase 2)."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_status_updates_message():
    from app.workers.wa_status_consumer import _handle_status

    with patch(
        "app.workers.wa_status_consumer.wa_inbox.update_message_status",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_upd:
        await _handle_status({"id": "wamid.1", "status": "read"})

    mock_upd.assert_called_once_with("wamid.1", "read")


@pytest.mark.asyncio
async def test_handle_status_unknown_message_no_raise():
    from app.workers.wa_status_consumer import _handle_status

    with patch(
        "app.workers.wa_status_consumer.wa_inbox.update_message_status",
        new_callable=AsyncMock,
        return_value=False,
    ):
        await _handle_status({"id": "wamid.x", "status": "delivered"})  # no exception


@pytest.mark.asyncio
async def test_handle_status_failed_branch():
    from app.workers.wa_status_consumer import _handle_status

    with patch(
        "app.workers.wa_status_consumer.wa_inbox.update_message_status",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_upd:
        await _handle_status({"id": "wamid.f", "status": "failed", "errors": [{"code": 131026}]})

    mock_upd.assert_called_once_with("wamid.f", "failed")


@pytest.mark.asyncio
async def test_handle_status_missing_fields_skips():
    from app.workers.wa_status_consumer import _handle_status

    with patch(
        "app.workers.wa_status_consumer.wa_inbox.update_message_status",
        new_callable=AsyncMock,
    ) as mock_upd:
        await _handle_status({"status": "read"})  # sin id
        await _handle_status({"id": "wamid.1"})  # sin status

    mock_upd.assert_not_called()


@pytest.mark.asyncio
async def test_handle_status_swallows_errors():
    from app.workers.wa_status_consumer import _handle_status

    with patch(
        "app.workers.wa_status_consumer.wa_inbox.update_message_status",
        new_callable=AsyncMock,
        side_effect=Exception("db down"),
    ):
        await _handle_status({"id": "wamid.1", "status": "read"})  # no propaga


@pytest.mark.asyncio
async def test_run_status_consumer_stops_on_event():
    from app.workers.wa_status_consumer import run_status_consumer

    stop_event = asyncio.Event()
    mock_redis = AsyncMock()
    mock_redis.blpop = AsyncMock(return_value=None)

    with patch("app.workers.wa_status_consumer.get_redis", return_value=mock_redis):
        stop_event.set()
        await asyncio.wait_for(run_status_consumer(stop_event), timeout=2)


@pytest.mark.asyncio
async def test_run_status_consumer_processes_queued_status():
    from app.workers.wa_status_consumer import run_status_consumer

    stop_event = asyncio.Event()
    payload = json.dumps({"id": "wamid.1", "status": "delivered"})

    mock_redis = AsyncMock()
    # primero entrega un status, luego para el loop
    mock_redis.blpop = AsyncMock(side_effect=[("whatsapp:statuses:incoming", payload), None])

    async def _stop_after(*_a, **_k):
        stop_event.set()
        return True

    with (
        patch("app.workers.wa_status_consumer.get_redis", return_value=mock_redis),
        patch(
            "app.workers.wa_status_consumer.wa_inbox.update_message_status",
            new=AsyncMock(side_effect=_stop_after),
        ) as mock_upd,
    ):
        await asyncio.wait_for(run_status_consumer(stop_event), timeout=2)

    mock_upd.assert_called_once_with("wamid.1", "delivered")
