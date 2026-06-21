"""Consumidor de status callbacks de WhatsApp (Fase 2 — delivery tracking).

Lee la cola `whatsapp:statuses:incoming` (poblada por el webhook) y actualiza
el estado de entrega del saliente correspondiente: sent | delivered | read | failed.
"""

import asyncio
import json

import structlog

from app.core.cache import get_redis
from app.services import wa_inbox

logger = structlog.get_logger()

_QUEUE_KEY = "whatsapp:statuses:incoming"
_BLPOP_TIMEOUT = 5


async def _handle_status(status: dict) -> None:
    wa_id: str = status.get("id", "")
    new_status: str = status.get("status", "")
    if not wa_id or not new_status:
        return
    try:
        updated = await wa_inbox.update_message_status(wa_id, new_status)
        if not updated:
            logger.debug("wa.status.unknown_message", message_id=wa_id, status=new_status)
        elif new_status == "failed":
            logger.warning("wa.status.failed", message_id=wa_id, errors=status.get("errors", []))
        else:
            logger.info("wa.status.updated", message_id=wa_id, status=new_status)
    except Exception as exc:
        logger.error("wa.status.error", message_id=wa_id, error=str(exc))


async def run_status_consumer(stop_event: asyncio.Event) -> None:
    logger.info("wa.status_consumer.started")
    redis = get_redis()
    while not stop_event.is_set():
        try:
            result = await redis.blpop(_QUEUE_KEY, timeout=_BLPOP_TIMEOUT)
            if result is None:
                continue
            _, raw = result
            await _handle_status(json.loads(raw))
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("wa.status_consumer.loop_error", error=str(exc))
            await asyncio.sleep(1)
    logger.info("wa.status_consumer.stopped")
