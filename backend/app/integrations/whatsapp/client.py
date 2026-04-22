import asyncio

import httpx
import structlog

from app.config import settings
from app.integrations.whatsapp.models import WASendResult

logger = structlog.get_logger()

_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503}


async def send_text_message(phone: str, text: str) -> WASendResult:
    return await send_whatsapp_message(phone=phone, text=text)


async def send_template_message(
    phone: str,
    template_name: str,
    variables: dict[str, str],
    language: str = "es",
) -> WASendResult:
    return await send_whatsapp_message(
        phone=phone,
        template_name=template_name,
        template_variables=variables,
        language=language,
    )


async def send_whatsapp_message(
    phone: str,
    text: str | None = None,
    template_name: str | None = None,
    template_variables: dict[str, str] | None = None,
    language: str = "es",
) -> WASendResult:
    if template_name:
        body = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(v)}
                            for v in (template_variables or {}).values()
                        ],
                    }
                ],
            },
        }
    else:
        body = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text},
        }

    url = f"{settings.WA_API_BASE}/{settings.WA_ACTIVE_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WA_ACCESS_TOKEN}"}

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=body, headers=headers)

            if r.status_code == 200:
                message_id = r.json()["messages"][0]["id"]
                logger.info("wa.sent", phone=phone, message_id=message_id)
                return WASendResult(message_id=message_id, status="sent")

            if r.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
                continue

            logger.error("wa.send_error", status=r.status_code, body=r.text)
            return WASendResult(
                message_id="",
                status="failed",
                error=f"HTTP {r.status_code}: {r.text[:200]}",
            )

        except httpx.RequestError as exc:
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
                continue
            return WASendResult(message_id="", status="failed", error=str(exc))

    return WASendResult(message_id="", status="failed", error="max retries exceeded")
