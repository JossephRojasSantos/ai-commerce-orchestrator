import structlog
from langchain_core.messages import AIMessage

from app.config import settings
from app.schemas.rag import RAGRequest
from app.services.orchestrator.state import ConversationState
from app.services.rag.recommendation import recommend

logger = structlog.get_logger()


async def run(state: ConversationState) -> dict:
    last = state["messages"][-1]
    user_text = last.content if hasattr(last, "content") else str(last)

    req = RAGRequest(
        query=user_text[:500],
        top_k=settings.RAG_TOP_K,
        min_score=settings.RAG_MIN_SCORE,
        generate=settings.RAG_LLM_ENABLED,
    )

    try:
        result = await recommend(req)
    except Exception as exc:
        logger.warning("reco_agent_rag_failed", error=str(exc), trace_id=state.get("trace_id"))
        reply = (
            "Lo siento, no pude consultar el catálogo en este momento. "
            "Por favor intenta de nuevo en unos segundos."
        )
        return {"messages": [AIMessage(content=reply)], "agent": "recommendation"}

    if result.answer:
        reply = result.answer
    elif result.hits:
        lines = [f"- {h.name} — ${h.price} ({h.permalink})" for h in result.hits[:5]]
        reply = "Encontré estos productos que podrían interesarte:\n" + "\n".join(lines)
    else:
        reply = (
            "No encontré productos que coincidan con tu búsqueda. "
            "¿Puedes darme más detalles sobre lo que buscas?"
        )

    logger.info(
        "reco_agent_replied",
        hits=len(result.hits),
        generated=result.answer is not None,
        latency_ms=result.latency_ms,
        trace_id=state.get("trace_id"),
    )
    return {"messages": [AIMessage(content=reply)], "agent": "recommendation"}
