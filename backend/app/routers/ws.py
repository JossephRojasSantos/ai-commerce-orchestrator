from __future__ import annotations

import json
import uuid

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.cache import get_redis
from app.services.orchestrator.graph import process_message

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])

_WELCOME = "¡Hola! Soy el asistente de Tienda Mágica. ¿En qué te puedo ayudar hoy?"


async def _persist_exchange(
    session_id: str, user_text: str, reply: str, intent: str, agent: str
) -> None:
    """Guarda el par usuario/asistente en las tablas de chat (feature 012, research R5).

    Best-effort: un fallo de DB no debe romper la conversación en vivo.
    """
    try:
        from sqlalchemy import select

        from app.db.base import AsyncSessionLocal
        from app.models.conversation import Conversation, Message

        async with AsyncSessionLocal() as db:
            sid = uuid.UUID(session_id)
            result = await db.execute(select(Conversation).where(Conversation.session_id == sid))
            conv = result.scalar_one_or_none()
            if conv is None:
                conv = Conversation(session_id=sid)
                db.add(conv)
                await db.flush()
            db.add(Message(conversation_id=conv.id, role="user", content=user_text))
            db.add(
                Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=reply,
                    metadata_={"intent": intent, "agent": agent},
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws_persist_failed", error=str(exc), session_id=session_id)


def _auth_ok(api_key: str) -> bool:
    if not settings.ALLOWED_API_KEYS:
        # Fail-closed en producción: sin keys configuradas nadie entra
        return settings.APP_ENV != "production"
    return api_key in settings.ALLOWED_API_KEYS


@router.websocket("/ws/chat")
async def ws_chat(
    websocket: WebSocket,
    api_key: str = Query(default="", alias="api_key"),
) -> None:
    if not _auth_ok(api_key):
        await websocket.close(code=4401)
        return

    await websocket.accept()

    session_id = str(uuid.uuid4())
    user_id = f"ws:{session_id}"
    trace_id = session_id
    client_ip = websocket.client.host if websocket.client else "unknown"

    logger.info("ws_chat_connected", session_id=session_id)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue

            msg_type = msg.get("type", "")

            if msg_type == "session_start":
                await websocket.send_text(json.dumps({"type": "text", "content": _WELCOME}))
                continue

            if msg_type != "message":
                continue

            text = (msg.get("content") or "").strip()
            if not text:
                continue

            # Rate-limit por IP antes de invocar el LLM (N2: acota coste y DoS)
            try:
                redis = get_redis()
                rate_key = f"ratelimit:ws:{client_ip}"
                count = await redis.incr(rate_key)
                if count == 1:
                    await redis.expire(rate_key, 60)
                if count > settings.WS_RATE_LIMIT_PER_MIN:
                    logger.warning("ws_chat_rate_limited", session_id=session_id, ip=client_ip)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "text",
                                "content": "Has enviado demasiados mensajes. Espera un momento e intenta de nuevo.",
                            }
                        )
                    )
                    continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("ws_ratelimit_unavailable", error=str(exc), session_id=session_id)

            await websocket.send_text(json.dumps({"type": "typing"}))

            intent = ""
            agent = ""
            try:
                result = await process_message(
                    channel="web",
                    user_id=user_id,
                    text=text,
                    trace_id=trace_id,
                    metadata={"session_id": session_id},
                )
                reply = result.get("reply", "")
                intent = result.get("intent", "")
                agent = result.get("agent", "")
            except Exception as exc:
                logger.error("ws_chat_error", error=str(exc), session_id=session_id)
                reply = "Lo siento, ocurrió un error. Por favor intenta de nuevo."

            await websocket.send_text(json.dumps({"type": "typing_stop"}))
            await websocket.send_text(json.dumps({"type": "text", "content": reply}))

            await _persist_exchange(session_id, text, reply, intent, agent)

            logger.info("ws_chat_replied", session_id=session_id, intent=intent)

    except WebSocketDisconnect:
        logger.info("ws_chat_disconnected", session_id=session_id)
