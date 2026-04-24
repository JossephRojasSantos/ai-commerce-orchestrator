import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.core.auth import require_api_key
from app.core.cache import get_redis
from app.schemas.orchestrator import MessageIn, MessageOut
from app.services.orchestrator.graph import process_message

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/orchestrator", tags=["orchestrator"])


@router.post("/message", response_model=MessageOut, dependencies=[Depends(require_api_key)])
async def orchestrate_message(body: MessageIn, request: Request) -> MessageOut:
    redis = get_redis()
    rate_key = f"ratelimit:orchestrator:{body.channel}:{body.user_id}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 60)
    if count > settings.ORCHESTRATOR_RATE_LIMIT_PER_MIN:
        logger.warning("orchestrator.rate_limited", user_id=body.user_id, channel=body.channel)
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")

    trace_id = getattr(request.state, "trace_id", "")
    result = await process_message(
        channel=body.channel,
        user_id=body.user_id,
        text=body.text,
        trace_id=trace_id,
        metadata=body.metadata,
    )
    return MessageOut(**result)
