from __future__ import annotations

import json
import uuid

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.orchestrator.graph import process_message

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])

_WELCOME = "¡Hola! Soy el asistente de Tienda Mágica. ¿En qué te puedo ayudar hoy?"


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

            await websocket.send_text(json.dumps({"type": "typing"}))

            try:
                result = await process_message(
                    channel="web",
                    user_id=user_id,
                    text=text,
                    trace_id=trace_id,
                    metadata={"session_id": session_id},
                )
                reply = result.get("reply", "")
            except Exception as exc:
                logger.error("ws_chat_error", error=str(exc), session_id=session_id)
                reply = "Lo siento, ocurrió un error. Por favor intenta de nuevo."

            await websocket.send_text(json.dumps({"type": "typing_stop"}))
            await websocket.send_text(json.dumps({"type": "text", "content": reply}))

            logger.info(
                "ws_chat_replied",
                session_id=session_id,
                intent=result.get("intent", "") if "result" in dir() else "",
            )

    except WebSocketDisconnect:
        logger.info("ws_chat_disconnected", session_id=session_id)
