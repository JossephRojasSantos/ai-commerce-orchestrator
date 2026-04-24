import structlog
from fastapi import Header, HTTPException

from app.config import settings

logger = structlog.get_logger()

_SKIP_AUTH_PREFIXES = (
    "/health",
    "/metrics",
    "/api/whatsapp",
    "/",
)


async def require_api_key(authorization: str = Header(..., alias="Authorization")) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token not in settings.ALLOWED_API_KEYS:
        logger.warning("auth.invalid_api_key")
        raise HTTPException(status_code=401, detail="unauthorized")
    return token
