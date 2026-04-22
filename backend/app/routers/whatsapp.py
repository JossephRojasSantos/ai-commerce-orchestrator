import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
import redis.asyncio as aioredis

from app.config import settings
from app.core.cache import get_redis

logger = structlog.get_logger()

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _verify_signature(body: bytes, signature_header: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.WA_APP_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> PlainTextResponse:
    if hub_mode == "subscribe" and hub_verify_token == settings.WA_WEBHOOK_VERIFY_TOKEN:
        logger.info("wa.webhook.verified")
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/webhook", status_code=200)
async def receive_webhook(request: Request) -> dict:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(body, signature):
        logger.warning("wa.webhook.invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    redis: Redis = get_redis()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            for message in change.get("value", {}).get("messages", []):
                message_id = message.get("id")
                if not message_id:
                    continue

                phone = message.get("from", "unknown")
                rate_key = f"ratelimit:whatsapp:{phone}"
                count = await redis.incr(rate_key)
                if count == 1:
                    await redis.expire(rate_key, 3600)
                if count > settings.WA_RATE_LIMIT_PER_HOUR:
                    logger.warning("wa.webhook.rate_limited", phone=phone, count=count)
                    continue

                was_set = await redis.set(
                    f"whatsapp:processed:{message_id}",
                    "1",
                    nx=True,
                    ex=86400,
                )
                if not was_set:
                    logger.debug("wa.webhook.duplicate", message_id=message_id)
                    continue

                await redis.rpush(
                    "whatsapp:messages:incoming",
                    json.dumps(message),
                )
                logger.info("wa.webhook.enqueued", message_id=message_id)

    return {"status": "received"}
