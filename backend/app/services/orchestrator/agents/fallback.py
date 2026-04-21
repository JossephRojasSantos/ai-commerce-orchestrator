import structlog
from langchain_core.messages import AIMessage

from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()

_REPLY = (
    "Hola, soy el asistente de Tienda Mágica. "
    "Puedo ayudarte a buscar productos, hacer un pedido o revisar el estado de tu compra. "
    "¿En qué te puedo ayudar?"
)


async def run(state: ConversationState) -> dict:
    logger.warning(
        "fallback_agent_triggered",
        intent=state.get("intent"),
        session_id=state.get("session_id"),
        trace_id=state.get("trace_id"),
    )
    return {"messages": [AIMessage(content=_REPLY)], "agent": "fallback"}
