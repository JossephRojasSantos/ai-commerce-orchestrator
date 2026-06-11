import unicodedata

import structlog
from langchain_core.messages import AIMessage

from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()

# Respuestas rápidas sin LLM: saludos, cortesía y FAQs de la tienda.
# El router manda estos mensajes con intent "other"; responder el saludo
# genérico a todo hacía parecer que el bot estaba roto.

_GREETINGS = {"hola", "holi", "holaa", "buenas", "hey", "hi", "hello", "saludos"}
_GREETING_PHRASES = ("buenos dias", "buenas tardes", "buenas noches", "que tal")
_THANKS = {"gracias", "genial", "perfecto", "vale", "listo", "excelente"}
_BYES = {"adios", "chao", "chau", "bye"}
_BYE_PHRASES = ("hasta luego", "nos vemos", "hasta pronto")

_FAQ_SHIPPING = ("envio", "envia", "entrega", "demora", "llega", "domicilio")
_FAQ_PAYMENT = (
    "pago",
    "pagar",
    "nequi",
    "pse",
    "daviplata",
    "addi",
    "tarjeta",
    "contraentrega",
    "efectivo",
)
_FAQ_RETURNS = ("devolucion", "devolver", "garantia", "cambio", "reembolso")

_REPLY_GREETING = (
    "¡Hola! 👋 Soy el asistente de Tienda Mágica. "
    "Puedo recomendarte productos, resolver dudas de envío o pagos, "
    "y revisar el estado de tu pedido. ¿Qué necesitas?"
)
_REPLY_THANKS = "¡Con mucho gusto! Si necesitas algo más, aquí estoy. 🪄"
_REPLY_BYE = "¡Hasta pronto! Vuelve cuando quieras. ✨"
_REPLY_SHIPPING = (
    "🚚 Hacemos envíos a toda Colombia en 24–72 horas. "
    "El envío es gratis en compras desde $120.000."
)
_REPLY_PAYMENT = (
    "💳 Aceptamos Nequi, PSE, Daviplata, Addi y pago contraentrega. "
    "Todos los pagos son 100% seguros."
)
_REPLY_RETURNS = (
    "↩️ Tienes 30 días para devoluciones. "
    "Escríbenos por WhatsApp y te acompañamos en el proceso."
)
_REPLY_DEFAULT = (
    "No estoy seguro de haber entendido. "
    "Puedo buscar productos, recomendarte algo según lo que necesites, "
    "o revisar el estado de tu pedido si me das el número. "
    "¿Puedes contarme un poco más?"
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").strip(" ¡!¿?.,")


def _resolve_reply(text: str) -> str:
    norm = _normalize(text)
    tokens = set(norm.split())

    if tokens & _GREETINGS or any(p in norm for p in _GREETING_PHRASES):
        return _REPLY_GREETING
    if tokens & _THANKS:
        return _REPLY_THANKS
    if tokens & _BYES or any(p in norm for p in _BYE_PHRASES):
        return _REPLY_BYE
    if any(k in norm for k in _FAQ_SHIPPING):
        return _REPLY_SHIPPING
    if any(k in norm for k in _FAQ_PAYMENT):
        return _REPLY_PAYMENT
    if any(k in norm for k in _FAQ_RETURNS):
        return _REPLY_RETURNS
    return _REPLY_DEFAULT


async def run(state: ConversationState) -> dict:
    last = state["messages"][-1]
    user_text = last.content if hasattr(last, "content") else str(last)
    reply = _resolve_reply(user_text)

    logger.warning(
        "fallback_agent_triggered",
        intent=state.get("intent"),
        session_id=state.get("session_id"),
        trace_id=state.get("trace_id"),
    )
    return {"messages": [AIMessage(content=reply)], "agent": "fallback"}
