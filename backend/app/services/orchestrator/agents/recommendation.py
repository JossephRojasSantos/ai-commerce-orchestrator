import structlog
from langchain_core.messages import AIMessage

from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()

# TODO: integrate AI-29 RAG endpoint when available
_RAG_ENDPOINT = "/v1/rag/recommend"


async def run(state: ConversationState) -> dict:
    last = state["messages"][-1]
    user_text = last.content if hasattr(last, "content") else str(last)

    reply = (
        "Aquí hay algunas sugerencias basadas en tu consulta. "
        "[Integración RAG (AI-29) pendiente — usando respuesta placeholder] "
        f"Consulta: «{user_text[:60]}»"
    )
    logger.info("reco_agent_replied", trace_id=state.get("trace_id"))
    return {"messages": [AIMessage(content=reply)], "agent": "recommendation"}
