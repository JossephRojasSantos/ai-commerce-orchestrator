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

        from app.core.tasks import spawn

        spawn(
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


async def _post_chat(
    client: httpx.AsyncClient, model: str, messages: list[dict], temperature: float
) -> dict:
    payload: dict = {"model": model, "messages": messages, "temperature": temperature}
    resp = await client.post(
        f"{settings.LLM_API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


async def chat_complete(
    messages: list[dict],
    model: str | None = None,
    fallback: str | None = None,
    temperature: float = 0.0,
) -> str:
    """Call OpenAI-compatible /chat/completions. Returns assistant content string.

    Reintenta el modelo primario una vez ante errores transitorios (timeout/5xx) y,
    si persisten, cae al modelo de fallback (N4). Los 4xx no se reintentan.
    """
    _model = model or settings.LLM_MODEL_CHAT
    _fallback = fallback or settings.LLM_FALLBACK_CHAT
    # primario, reintento del primario, y por último el fallback (si difiere)
    candidates = [_model, _model]
    if _fallback and _fallback != _model:
        candidates.append(_fallback)

    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        for attempt, m in enumerate(candidates):
            try:
                data = await _post_chat(client, m, messages, temperature)
                _record_usage_background(data)
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                status = getattr(exc.response, "status_code", None)
                if isinstance(status, int) and status < 500:
                    raise  # error del cliente (4xx): reintentar/fallback no ayuda
                last_exc = exc
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
            logger.warning("llm.retry", model=m, attempt=attempt, error=str(last_exc))

    assert last_exc is not None
    raise last_exc


async def multimodal_complete(
    content: list[dict],
    model: str,
    temperature: float = 0.0,
) -> str:
    """Una sola vuelta multimodal: un mensaje user con partes (text/image_url/input_audio).

    Usado para interpretar adjuntos de WhatsApp (Fase 3). El formato de `content`
    sigue la API OpenAI-compatible de OpenRouter.
    """
    messages = [{"role": "user", "content": content}]
    payload: dict = {"model": model, "messages": messages, "temperature": temperature}
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
