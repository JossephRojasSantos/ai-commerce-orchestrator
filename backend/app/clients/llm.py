import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


async def chat_complete(messages: list[dict], temperature: float = 0.0) -> str:
    """Call OpenAI-compatible /chat/completions. Returns assistant content string."""
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.LLM_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json={
                "model": settings.LLM_MODEL,
                "messages": messages,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
