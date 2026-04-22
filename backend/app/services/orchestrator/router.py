import json
import re
from enum import Enum

import structlog

from app.clients.llm import chat_complete
from app.core.cache import cache_get, cache_set
from app.config import settings

logger = structlog.get_logger()

_TRACKING_RE = re.compile(r"(pedido|order|tracking|envío|envio)\s*#?\d*", re.IGNORECASE)
_BUY_RE = re.compile(r"(comprar|quiero|precio|costo|cuánto|cuanto|agregar|carrito)", re.IGNORECASE)
_RECOMMEND_RE = re.compile(r"(recomienda|sugerir|qué me|que me|busco algo|similar)", re.IGNORECASE)

_CLASSIFIER_PROMPT = (
    "Classify the user message into exactly one intent.\n"
    'Respond with ONLY the JSON: {{"intent": "<intent>", "confidence": <0.0-1.0>}}\n'
    "Valid intents: buy, track, recommend, other\n\n"
    "Examples:\n"
    '- "quiero comprar zapatos" -> {{"intent": "buy", "confidence": 0.95}}\n'
    '- "donde esta mi pedido 123" -> {{"intent": "track", "confidence": 0.97}}\n'
    '- "que me recomiendas" -> {{"intent": "recommend", "confidence": 0.90}}\n'
    '- "hola, buenos dias" -> {{"intent": "other", "confidence": 0.85}}\n\n'
    "User message: {text}"
)


class Intent(str, Enum):
    BUY = "buy"
    TRACK = "track"
    RECOMMEND = "recommend"
    OTHER = "other"


class RouterResult:
    __slots__ = ("intent", "confidence")

    def __init__(self, intent: Intent, confidence: float):
        self.intent = intent
        self.confidence = confidence


def _regex_fallback(text: str) -> RouterResult | None:
    if _TRACKING_RE.search(text):
        return RouterResult(Intent.TRACK, 0.75)
    if _BUY_RE.search(text):
        return RouterResult(Intent.BUY, 0.70)
    if _RECOMMEND_RE.search(text):
        return RouterResult(Intent.RECOMMEND, 0.70)
    return None


async def classify_intent(text: str, session_id: str) -> RouterResult:
    cache_key = f"intent:{session_id}:{hash(text)}"
    cached = await cache_get(cache_key)
    if cached:
        return RouterResult(Intent(cached["intent"]), cached["confidence"])

    try:
        raw = await chat_complete(
            [{"role": "user", "content": _CLASSIFIER_PROMPT.format(text=text)}],
            model=settings.LLM_MODEL_ROUTER,
            fallback=settings.LLM_FALLBACK_ROUTER,
            temperature=0.0,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        intent = Intent(data.get("intent", "other"))
        confidence = float(data.get("confidence", 0.5))
        result = RouterResult(intent, confidence)
        await cache_set(cache_key, {"intent": intent.value, "confidence": confidence}, settings.INTENT_CACHE_TTL)
        return result
    except Exception as exc:
        logger.warning("intent_llm_failed", error=str(exc), text=text[:80])
        fallback = _regex_fallback(text)
        if fallback:
            return fallback
        return RouterResult(Intent.OTHER, 0.5)
