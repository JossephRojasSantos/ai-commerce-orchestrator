import structlog
from langchain_core.messages import AIMessage, HumanMessage

from app.clients.llm import chat_complete
from app.config import settings
from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()

_SYSTEM = (
    "Eres un asistente de ventas de Tienda Mágica. "
    "Ayuda al usuario a encontrar y comprar productos. "
    "Responde en español, sé conciso y amigable."
)


async def run(state: ConversationState) -> dict:
    history = []
    for msg in state["messages"][:-1]:
        if isinstance(msg, HumanMessage):
            history.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            history.append({"role": "assistant", "content": msg.content})

    last = state["messages"][-1]
    user_text = last.content if hasattr(last, "content") else str(last)

    messages = (
        [{"role": "system", "content": _SYSTEM}]
        + history
        + [{"role": "user", "content": user_text}]
    )

    reply = await chat_complete(
        messages,
        model=settings.LLM_MODEL_CHAT,
        fallback=settings.LLM_FALLBACK_CHAT,
    )
    logger.info(
        "chat_agent_replied", session_id=state.get("session_id"), trace_id=state.get("trace_id")
    )
    return {"messages": [AIMessage(content=reply)], "agent": "chat"}
