import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


async def chat_complete(
    messages: list[dict],
    model: str | None = None,
    fallback: str | None = None,
    temperature: float = 0.0,
) -> str:
    """Call OpenRouter /chat/completions. Returns assistant content string."""
    _model = model or settings.LLM_MODEL_CHAT
    payload: dict = {"model": _model, "messages": messages, "temperature": temperature}
    if fallback:
        payload["models"] = [_model, fallback]
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.LLM_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "HTTP-Referer": settings.OPENROUTER_REFERER,
                "X-Title": settings.OPENROUTER_APP_NAME,
                "X-OR-Prompt-Training": "false",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
