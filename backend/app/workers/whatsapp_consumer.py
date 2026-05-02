import asyncio
import contextlib
import json
import uuid

import structlog

from app.core.cache import get_redis
from app.integrations.whatsapp.client import send_text_message
from app.services.orchestrator.graph import process_message

logger = structlog.get_logger()

_QUEUE_KEY = "whatsapp:messages:incoming"
_BLPOP_TIMEOUT = 5


async def _handle(message: dict) -> None:
    phone: str = message.get("from", "")
    msg_type: str = message.get("type", "")

    if msg_type == "text":
        text: str = message.get("text", {}).get("body", "")
    elif msg_type == "button":
        text = message.get("button", {}).get("text", "")
    else:
        logger.info("wa.consumer.unsupported_type", msg_type=msg_type, phone=phone)
        return

    if not phone or not text:
        return

    trace_id = str(uuid.uuid4())
    try:
        result = await process_message(
            channel="whatsapp",
            user_id=phone,
            text=text,
            trace_id=trace_id,
        )
        await send_text_message(phone=phone, text=result["reply"])
        logger.info(
            "wa.consumer.replied",
            phone=phone,
            trace_id=trace_id,
            agent=result.get("agent"),
            intent=result.get("intent"),
        )
    except Exception as exc:
        logger.error("wa.consumer.error", phone=phone, trace_id=trace_id, error=str(exc))
        with contextlib.suppress(Exception):
            await send_text_message(
                phone=phone,
                text="Lo siento, ocurrió un error. Por favor intenta de nuevo en unos minutos.",
            )


async def run_consumer(stop_event: asyncio.Event) -> None:
    logger.info("wa.consumer.started")
    redis = get_redis()
    while not stop_event.is_set():
        try:
            result = await redis.blpop(_QUEUE_KEY, timeout=_BLPOP_TIMEOUT)
            if result is None:
                continue
            _, raw = result
            message = json.loads(raw)
            asyncio.create_task(_handle(message))
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("wa.consumer.loop_error", error=str(exc))
            await asyncio.sleep(1)
    logger.info("wa.consumer.stopped")
