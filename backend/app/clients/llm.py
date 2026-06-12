import asyncio

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


def _record_usage_background(data: dict) -> None:
    """Registra el consumo de tokens sin bloquear ni romper la respuesta (research R1)."""
    try:
        from app.services.admin.ai_usage import record_usage

        usage = data.get("usage") or {}
        model = data.get("model", "")
        if not usage or not model:
            return

        # session/channel best-effort desde los contextvars de structlog
        ctx = structlog.contextvars.get_contextvars()
        session_id = ctx.get("session_id") or ctx.get("trace_id")
        channel = ctx.get("channel")

        asyncio.get_running_loop().create_task(
            record_usage(
                model=model,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                session_id=str(session_id) if session_id else None,
                channel=str(channel) if channel else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_usage.schedule_failed", error=str(exc))


async def chat_complete(
    messages: list[dict],
    model: str | None = None,
    fallback: str | None = None,
    temperature: float = 0.0,
) -> str:
    """Call OpenAI-compatible /chat/completions. Returns assistant content string."""
    _model = model or settings.LLM_MODEL_CHAT
    payload: dict = {"model": _model, "messages": messages, "temperature": temperature}
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.LLM_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        _record_usage_background(data)
        return data["choices"][0]["message"]["content"]
