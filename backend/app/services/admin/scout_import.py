"""Importar un producto del catálogo Dropi a WooCommerce con un clic (feature 014).

Crea el producto en la tienda y deja la meta que el plugin Dropi necesita para
sincronizar las órdenes (`_dropi_product`, `_dropi_token`, etc.). El plugin hace
`unserialize()` y, si falla, cae a `json_decode()` — así que la meta se guarda
como JSON desde el backend (verificado en OrdersModel::makeProductsArray).
"""

import json

import structlog

from app.clients import dropi
from app.clients.woocommerce import get_wc_client
from app.config import settings

logger = structlog.get_logger()

TOKEN_STORE_LABEL = "Tienda Mágica"


def _dropi_meta_object(detail: dict) -> dict:
    """Objeto que el order-sync del plugin lee de `_dropi_product` (campos mínimos)."""
    user = detail.get("user") or {}
    return {
        "id": detail.get("id"),
        "name": detail.get("name"),
        "sku": detail.get("sku"),
        "type": detail.get("type") or "SIMPLE",
        "stock": dropi.stock_total(detail),
        "sale_price": detail.get("sale_price"),
        "suggested_price": detail.get("suggested_price"),
        "user_id": detail.get("user_id") or user.get("id"),
        "variations": detail.get("variations") or [],
    }


def _strip_html_keep_basic(html: str) -> str:
    return html or ""


async def import_product(dropi_product_id: int) -> dict:
    """Crea el producto en WooCommerce. Idempotente por SKU.

    Devuelve {status: created|exists, wc_id, name, permalink}.
    """
    if not settings.DROPI_INTEGRATION_KEY:
        raise RuntimeError("DROPI_INTEGRATION_KEY no configurado")

    detail = await dropi.get_product_detail(dropi_product_id)
    sku = detail.get("sku") or f"DROPI-{dropi_product_id}"
    name = detail.get("name") or f"Producto Dropi {dropi_product_id}"
    suggested = detail.get("suggested_price")

    wc = await get_wc_client()

    existing = await wc.find_product_by_sku(sku)
    if existing:
        return {
            "status": "exists",
            "wc_id": existing.get("id"),
            "name": existing.get("name"),
            "permalink": existing.get("permalink"),
        }

    images = [{"src": u} for u in dropi.image_urls(detail)]
    categories_meta = detail.get("categories") or []
    payload = {
        "name": name,
        "type": "simple",
        "status": "draft",  # se publica tras revisar precio/fotos
        "regular_price": str(int(float(suggested))) if suggested else "",
        "sku": sku,
        "description": _strip_html_keep_basic(
            detail.get("description") or detail.get("dropi_app_description") or ""
        ),
        "manage_stock": True,
        "stock_quantity": dropi.stock_total(detail),
        "images": images,
        "meta_data": [
            {"key": "_dropi_product", "value": json.dumps(_dropi_meta_object(detail))},
            {"key": "_dropi_product_id", "value": str(dropi_product_id)},
            {"key": "_dropi_token", "value": settings.DROPI_INTEGRATION_KEY},
            {"key": "_dropi_token_store", "value": TOKEN_STORE_LABEL},
        ],
    }
    if categories_meta:
        # WC necesita ids de categoría propios; si no mapean, se omite (queda sin categoría)
        pass

    from app.clients.woocommerce import WCClientError

    images_ok = True
    try:
        created = await wc.create_product(payload)
    except WCClientError as exc:
        # El CDN/WAF de Dropi bloquea la descarga server-side de fotos desde Hostinger;
        # si WC no puede traer la imagen, se importa sin ella (el usuario la sube luego).
        if "image" not in (exc.message or "").lower():
            raise
        images_ok = False
        payload["images"] = []
        created = await wc.create_product(payload)

    logger.info(
        "scout.imported", dropi_id=dropi_product_id, wc_id=created.get("id"), images=images_ok
    )
    return {
        "status": "created",
        "wc_id": created.get("id"),
        "name": created.get("name"),
        "permalink": created.get("permalink"),
        "images_imported": images_ok,
    }
