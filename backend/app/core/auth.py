import hmac

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


def _key_matches(token: str, allowed: list[str]) -> bool:
    """Comparación en tiempo constante contra cada key permitida (evita timing side-channel)."""
    return any(hmac.compare_digest(token, k) for k in allowed)


async def require_api_key(authorization: str = Header(..., alias="Authorization")) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not _key_matches(token, settings.ALLOWED_API_KEYS):
        logger.warning("auth.invalid_api_key")
        raise HTTPException(status_code=401, detail="unauthorized")
    return token


async def require_internal_api_key(authorization: str = Header(..., alias="Authorization")) -> str:
    """Autorización elevada para endpoints con PII (órdenes). Solo keys server-to-server.

    La key pública (chat/RAG) expuesta al navegador NO pasa este control, cerrando el IDOR
    de enumeración de pedidos por ``?customer=``.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not _key_matches(token, settings.INTERNAL_API_KEYS):
        logger.warning("auth.invalid_internal_api_key")
        raise HTTPException(status_code=403, detail="forbidden")
    return token
