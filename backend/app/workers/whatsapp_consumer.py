import asyncio
import contextlib
import json
import uuid

import structlog

from app.config import settings
from app.core.cache import get_redis
from app.core.tasks import spawn
from app.integrations.whatsapp.client import send_text_message
from app.services import wa_inbox
from app.services.orchestrator.graph import process_message

logger = structlog.get_logger()

_QUEUE_KEY = "whatsapp:messages:incoming"
_BLPOP_TIMEOUT = 5

# Acota cuántos mensajes se procesan en paralelo para no disparar fan-out de LLM (N3)
_semaphore = asyncio.Semaphore(settings.WA_CONSUMER_MAX_CONCURRENCY)


async def _handle_bounded(message: dict) -> None:
    async with _semaphore:
        await _handle(message)


# Placeholder legible por tipo para no perder contexto del hilo (feature 013)
_MEDIA_LABELS = {
    "image": "[imagen]",
    "audio": "[audio]",
    "voice": "[nota de voz]",
    "video": "[video]",
    "document": "[documento]",
    "sticker": "[sticker]",
    "location": "[ubicación]",
    "contacts": "[contacto]",
}


def _media_placeholder(message: dict, msg_type: str) -> str:
    """Etiqueta legible + caption del adjunto si viene."""
    label = _MEDIA_LABELS.get(msg_type, f"[{msg_type or 'mensaje no soportado'}]")
    caption = (message.get(msg_type) or {}).get("caption", "")
    return f"{label} {caption}".strip() if caption else label


async def _handle(message: dict) -> None:
    phone: str = message.get("from", "")
    msg_type: str = message.get("type", "")
    profile_name: str = message.get("profile_name", "")

    text: str = ""
    if msg_type == "text":
        text = message.get("text", {}).get("body", "")
    elif msg_type == "button":
        text = message.get("button", {}).get("text", "")
    elif settings.WA_MEDIA_ENABLED and msg_type in ("image", "audio", "voice"):
        # Fase 3 — interpreta el adjunto a texto vía LLM multimodal
        from app.integrations.whatsapp.media import media_to_text

        with contextlib.suppress(Exception):
            text = await media_to_text(message, msg_type)
        if text:
            logger.info("wa.consumer.media_interpreted", msg_type=msg_type, phone=phone)

    if not text and msg_type not in ("text", "button"):
        logger.info("wa.consumer.unsupported_type", msg_type=msg_type, phone=phone)
        # Persistir placeholder type-aware para que el hilo no pierda contexto (feature 013)
        if phone:
            with contextlib.suppress(Exception):
                await wa_inbox.record_incoming(
                    phone, _media_placeholder(message, msg_type), name=profile_name or None
                )
        return

    if not phone or not text:
        return

    # Persistir el entrante SIEMPRE (aparece en el inbox admin), y decidir si el
    # bot responde (modo humano — FR-011). El kill switch se evalúa DESPUÉS para
    # no perder mensajes: con el bot apagado igual entran a la bandeja.
    bot_should_reply = True
    try:
        bot_should_reply = await wa_inbox.record_incoming(phone, text, name=profile_name or None)
    except Exception as exc:  # noqa: BLE001 — la persistencia no bloquea al bot
        logger.warning("wa.consumer.persist_failed", phone=phone, error=str(exc))

    if not settings.WA_BOT_ENABLED:
        logger.info("wa.consumer.bot_disabled_skip", phone=phone)
        return

    if not bot_should_reply:
        logger.info("wa.consumer.human_mode_skip", phone=phone)
        return

    trace_id = str(uuid.uuid4())
    try:
        result = await process_message(
            channel="whatsapp",
            user_id=phone,
            text=text,
            trace_id=trace_id,
        )
        send_result = await send_text_message(phone=phone, text=result["reply"])
        with contextlib.suppress(Exception):
            await wa_inbox.record_outgoing(
                phone,
                result["reply"],
                author="bot",
                delivered=send_result.status == "sent",
                wa_message_id=send_result.message_id or None,
            )
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
            spawn(_handle_bounded(message))
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("wa.consumer.loop_error", error=str(exc))
            await asyncio.sleep(1)
    logger.info("wa.consumer.stopped")
