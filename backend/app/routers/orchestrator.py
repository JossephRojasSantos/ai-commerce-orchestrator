import structlog
from fastapi import APIRouter, Request

from app.schemas.orchestrator import MessageIn, MessageOut
from app.services.orchestrator.graph import process_message

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/orchestrator", tags=["orchestrator"])


@router.post("/message", response_model=MessageOut)
async def orchestrate_message(body: MessageIn, request: Request) -> MessageOut:
    trace_id = getattr(request.state, "trace_id", "")
    result = await process_message(
        channel=body.channel,
        user_id=body.user_id,
        text=body.text,
        trace_id=trace_id,
        metadata=body.metadata,
    )
    return MessageOut(**result)
