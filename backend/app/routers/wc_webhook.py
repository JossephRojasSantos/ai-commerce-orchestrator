from __future__ import annotations

import base64
import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config import settings
from app.services.rag.indexer import delete_product, index_product

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(body: bytes, signature_header: str) -> bool:
    if not signature_header:
        return False
    expected = base64.b64encode(
        hmac.new(settings.WC_WEBHOOK_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature_header)


@router.post("/wc", status_code=200)
async def receive_wc_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    body = await request.body()
    signature = request.headers.get("X-WC-Webhook-Signature", "")
    topic = request.headers.get("X-WC-Webhook-Topic", "")

    if settings.WC_WEBHOOK_SECRET and not _verify_signature(body, signature):
        logger.warning("wc_webhook_invalid_signature", topic=topic)
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        logger.warning("wc_webhook_invalid_json", topic=topic)
        payload = {}

    product_id = payload.get("id")
    logger.info("wc_webhook_received", topic=topic, product_id=product_id)

    if topic in ("product.created", "product.updated"):
        background_tasks.add_task(index_product, payload)
    elif topic == "product.deleted":
        if product_id:
            background_tasks.add_task(delete_product, product_id)
    else:
        logger.info("wc_webhook_unknown_topic", topic=topic)

    return {"ok": True}
