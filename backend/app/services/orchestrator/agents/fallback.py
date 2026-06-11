import structlog
from langchain_core.messages import AIMessage

from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()

_REPLY = (
    "No estoy seguro de haber entendido. "
    "Puedo buscar productos, recomendarte algo según lo que necesites, "
    "o revisar el estado de tu pedido si me das el número. "
    "¿Puedes contarme un poco más?"
)


async def run(state: ConversationState) -> dict:
    logger.warning(
        "fallback_agent_triggered",
        intent=state.get("intent"),
        session_id=state.get("session_id"),
        trace_id=state.get("trace_id"),
    )
    return {"messages": [AIMessage(content=_REPLY)], "agent": "fallback"}
