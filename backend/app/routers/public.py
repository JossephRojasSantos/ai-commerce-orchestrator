"""Rutas públicas sin auth — solo el blob de creativos que WooCommerce descarga.

WooCommerce (en Hostinger) hace un GET server-to-server a esta URL para bajar la
imagen subida por el admin; por eso no puede llevar la sesión admin. El contenido
es efímero (Redis TTL) y solo accesible con el uuid aleatorio del creativo.
"""

from fastapi import APIRouter, HTTPException, Response

router = APIRouter(prefix="/v1/public", tags=["public"])


@router.get("/media/{media_id}")
async def get_media(media_id: str) -> Response:
    from app.services.admin import media_store

    item = await media_store.get_image(media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="not_found") from None
    content, mime = item
    return Response(
        content=content, media_type=mime, headers={"Cache-Control": "public, max-age=3600"}
    )
