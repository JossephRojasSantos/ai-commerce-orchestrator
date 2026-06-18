"""Descarga e interpretación de adjuntos de WhatsApp (Fase 3).

Flujo Graph API: media_id -> GET /{media_id} (url + mime) -> GET url (bytes).
La interpretación delega en un LLM multimodal (visión / audio) y devuelve texto
en español que el orquestador trata como un mensaje normal del cliente.

Todo es best-effort: ante cualquier fallo se devuelve "" y el consumidor cae al
placeholder type-aware.
"""

import base64

import httpx
import structlog

from app.clients.llm import multimodal_complete
from app.config import settings

logger = structlog.get_logger()

_IMAGE_PROMPT = (
    "Un cliente envió esta imagen por WhatsApp a una tienda online. Describe en "
    "español, en una frase, qué muestra. Si contiene texto relevante (pedido, "
    "código, dirección, comprobante), transcríbelo."
)
_AUDIO_PROMPT = (
    "Transcribe en español la nota de voz de un cliente de una tienda online. "
    "Devuelve solo la transcripción, sin comentarios."
)


async def download_media(media_id: str) -> tuple[bytes, str]:
    """Descarga un adjunto. Devuelve (bytes, mime_type) o (b"", "") si falla/excede tamaño."""
    if not media_id:
        return (b"", "")
    headers = {"Authorization": f"Bearer {settings.WA_ACCESS_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            meta = await client.get(f"{settings.WA_API_BASE}/{media_id}", headers=headers)
            meta.raise_for_status()
            info = meta.json()
            url = info.get("url", "")
            mime = info.get("mime_type", "")
            if not url:
                return (b"", "")
            if int(info.get("file_size", 0)) > settings.WA_MEDIA_MAX_BYTES:
                logger.warning("wa.media.too_large", media_id=media_id, size=info.get("file_size"))
                return (b"", "")
            blob = await client.get(url, headers=headers)
            blob.raise_for_status()
            data = blob.content
            if len(data) > settings.WA_MEDIA_MAX_BYTES:
                return (b"", "")
            return (data, mime)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("wa.media.download_failed", media_id=media_id, error=str(exc))
        return (b"", "")


async def interpret_media(msg_type: str, data: bytes, mime: str) -> str:
    """Interpreta el adjunto con un LLM multimodal. Devuelve texto español o ""."""
    if not data:
        return ""
    b64 = base64.b64encode(data).decode()
    try:
        if msg_type == "image":
            content = [
                {"type": "text", "text": _IMAGE_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]
            return (await multimodal_complete(content, settings.LLM_MODEL_VISION)).strip()
        if msg_type in ("audio", "voice"):
            fmt = (mime.split("/")[-1] or "ogg").split(";")[0]
            content = [
                {"type": "text", "text": _AUDIO_PROMPT},
                {"type": "input_audio", "input_audio": {"data": b64, "format": fmt}},
            ]
            return (await multimodal_complete(content, settings.LLM_MODEL_AUDIO)).strip()
    except httpx.HTTPError as exc:
        logger.warning("wa.media.interpret_failed", msg_type=msg_type, error=str(exc))
    return ""


async def media_to_text(message: dict, msg_type: str) -> str:
    """Resuelve un adjunto a texto: extrae media_id, descarga e interpreta."""
    media_id = (message.get(msg_type) or {}).get("id", "")
    data, mime = await download_media(media_id)
    return await interpret_media(msg_type, data, mime)
