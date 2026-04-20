"""
Mock WebSocket server — Chat Widget
Simula el agente para desarrollo local.

Requiere: pip install websockets
Uso:      python chat_ws_mock.py
          WS disponible en ws://localhost:8080
"""

import asyncio
import json
import logging
from datetime import datetime

import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("chat-mock")

# Respuestas automáticas del mock
RESPONSES = {
    "hola":    "¡Hola! Soy el asistente de Tienda Mágica ✨ ¿En qué te puedo ayudar?",
    "precio":  "Puedo ayudarte con precios. ¿Qué producto te interesa?",
    "envio":   "Los envíos tienen un costo de $50 MXN y llegan en 3–5 días hábiles.",
    "default": "Entendido. En breve un agente real responderá tu pregunta.",
}

CONNECTED: set[websockets.WebSocketServerProtocol] = set()


async def send_json(ws, obj: dict):
    await ws.send(json.dumps(obj, ensure_ascii=False))


async def handler(ws: websockets.WebSocketServerProtocol):
    CONNECTED.add(ws)
    log.info(f"Cliente conectado — total: {len(CONNECTED)}")

    # Saludo proactivo
    await asyncio.sleep(0.5)
    await send_json(ws, {
        "type": "text",
        "content": "¡Bienvenido a Tienda Mágica! ¿Tienes alguna pregunta sobre nuestros productos? 🛍️",
    })

    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")
            log.info(f"← {msg_type}: {data}")

            if msg_type == "session_start":
                log.info(f"  URL: {data.get('url')}")
                continue

            if msg_type == "message":
                content = data.get("content", "").lower()

                # Simular "escribiendo…"
                await send_json(ws, {"type": "typing"})
                await asyncio.sleep(1)
                await send_json(ws, {"type": "typing_stop"})

                # Elegir respuesta
                reply = next(
                    (v for k, v in RESPONSES.items() if k != "default" and k in content),
                    RESPONSES["default"],
                )
                await send_json(ws, {"type": "text", "content": reply})

    except websockets.ConnectionClosed:
        pass
    finally:
        CONNECTED.discard(ws)
        log.info(f"Cliente desconectado — total: {len(CONNECTED)}")


async def broadcast_alert(message: str):
    """Envía alerta proactiva a todos los clientes conectados."""
    if not CONNECTED:
        return
    payload = json.dumps({"type": "alert", "content": message}, ensure_ascii=False)
    await asyncio.gather(*(ws.send(payload) for ws in CONNECTED), return_exceptions=True)


async def demo_alerts():
    """Alertas proactivas de ejemplo cada 30 s — quitar en producción."""
    alerts = [
        "🔥 ¡Oferta relámpago! 20% en juguetes educativos — solo hoy.",
        "⚡ Últimas 3 unidades del Kit Mágico Deluxe.",
        "🎉 ¡Tu carrito tiene artículos con descuento disponible!",
    ]
    idx = 0
    await asyncio.sleep(15)
    while True:
        await broadcast_alert(alerts[idx % len(alerts)])
        idx += 1
        await asyncio.sleep(30)


async def main():
    async with websockets.serve(handler, "localhost", 8765):
        log.info("Mock WS server en ws://localhost:8765 — Ctrl+C para detener")
        await asyncio.gather(demo_alerts())


if __name__ == "__main__":
    asyncio.run(main())
