import re

import structlog
from langchain_core.messages import AIMessage

from app.clients.woocommerce import WCClientError, WCServerError, get_wc_client
from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()

_ORDER_RE = re.compile(r"#?(\d{3,})")


def _extract_order_id(text: str) -> str | None:
    m = _ORDER_RE.search(text)
    return m.group(1) if m else None


async def run(state: ConversationState) -> dict:
    last = state["messages"][-1]
    user_text = last.content if hasattr(last, "content") else str(last)
    order_id = _extract_order_id(user_text)

    if not order_id:
        reply = "¿Cuál es el número de tu pedido? Puedes encontrarlo en tu correo de confirmación."
        return {"messages": [AIMessage(content=reply)], "agent": "tracking"}

    try:
        wc = await get_wc_client()
        order = await wc._get(f"/orders/{order_id}")
        status_map = {
            "pending": "pendiente de pago",
            "processing": "en proceso",
            "on-hold": "en espera",
            "completed": "completado",
            "cancelled": "cancelado",
            "refunded": "reembolsado",
            "failed": "fallido",
        }
        status = status_map.get(order.get("status", ""), order.get("status", "desconocido"))
        reply = f"Tu pedido #{order_id} está **{status}**."
        if order.get("date_created"):
            reply += f" Fecha: {order['date_created'][:10]}."
    except (WCClientError, WCServerError) as exc:
        logger.warning("tracking_wc_error", order_id=order_id, error=str(exc))
        reply = f"No pude obtener información del pedido #{order_id}. Intenta más tarde."

    logger.info("tracking_agent_replied", order_id=order_id, trace_id=state.get("trace_id"))
    return {"messages": [AIMessage(content=reply)], "agent": "tracking"}
