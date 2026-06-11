import structlog
from langchain_core.messages import AIMessage, HumanMessage

from app.clients.llm import chat_complete
from app.config import settings
from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()

_SYSTEM = (
    "Eres el asistente de ventas de Tienda Mágica (tiendamagica.shop), "
    "una tienda colombiana de productos útiles para cocina, hogar y tecnología.\n"
    "Datos de la tienda: envío a toda Colombia en 24–72h, gratis en compras desde $120.000; "
    "pagos con Nequi, PSE, Daviplata, Addi y contraentrega; devoluciones dentro de 30 días.\n"
    "Reglas:\n"
    "- Responde en español, cálido y conciso (máximo 2 párrafos cortos).\n"
    "- NUNCA inventes nombres de productos, precios ni enlaces. "
    "No tienes acceso al catálogo en esta conversación: si el cliente pide un producto "
    "concreto, pídele detalles de lo que necesita y dile que puedes recomendarle "
    "opciones del catálogo (por ejemplo: '¿para qué lo necesitas? Así te recomiendo el ideal').\n"
    "- Si preguntan por su pedido, pide el número de pedido."
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
