"""Almacén temporal de creativos subidos por el admin (feature 015).

El admin sube una imagen → se guarda en Redis con TTL → se expone una URL pública
→ WooCommerce la descarga a su librería de medios (mismo patrón src-by-URL que ya
usa el import). Tras la descarga, el blob expira solo. Evita volúmenes persistentes
y cambios de nginx (la ruta vive bajo /v1 que ya se enruta al backend).
"""

import base64
import uuid

import redis.asyncio as aioredis

from app.config import settings

MEDIA_TTL = 3600  # 1h — WC la descarga en el mismo request; el TTL es colchón
MAX_BYTES = 8 * 1024 * 1024  # 8 MB por creativo
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _redis():
    return aioredis.from_url(settings.REDIS_URL, decode_responses=False)


async def store_image(content: bytes, mime: str) -> str:
    """Guarda el creativo y devuelve su id (uuid)."""
    media_id = uuid.uuid4().hex
    r = _redis()
    try:
        # value = mime\n + bytes
        payload = mime.encode() + b"\n" + content
        await r.set(f"media:{media_id}", base64.b64encode(payload), ex=MEDIA_TTL)
    finally:
        await r.aclose()
    return media_id


async def get_image(media_id: str) -> tuple[bytes, str] | None:
    r = _redis()
    try:
        raw = await r.get(f"media:{media_id}")
    finally:
        await r.aclose()
    if not raw:
        return None
    decoded = base64.b64decode(raw)
    mime, _, content = decoded.partition(b"\n")
    return content, mime.decode()


def public_url(media_id: str) -> str:
    return f"{settings.PUBLIC_API_BASE}/v1/public/media/{media_id}"
