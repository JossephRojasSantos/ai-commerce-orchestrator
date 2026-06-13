"""Cliente de la API de integraciones de Dropi (feature 014, research R1).

El WAF de Dropi rechaza User-Agents de CLI/librerías con 401 "Access denied"
aunque el token sea válido — se envía un UA tipo WordPress (validado en vivo).
El token jamás se loguea ni sale del backend (FR-014).
"""

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

PAGE_SIZE = 100


def _headers(key: str | None = None) -> dict:
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": settings.DROPI_USER_AGENT,
        "dropi-integration-key": key or settings.DROPI_INTEGRATION_KEY,
    }


async def list_products(start: int, category_id: int | None = None) -> list[dict]:
    """Una página del catálogo filtrado (activos, con stock, proveedores verificados).

    `start` es el offset (`startData`). Devuelve [] al llegar al final.
    """
    payload: dict = {
        "startData": start,
        "pageSize": PAGE_SIZE,
        "order_type": "desc",
        "order_by": "created_at",
        "keywords": "",
        "active": True,
        "no_count": True,
        "integration": True,
        "get_stock": False,  # requerido en api.dropi.co (R1)
        "stockmayor": 1,
        "userVerified": True,
    }
    if category_id is not None:
        payload["category"] = category_id

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.DROPI_API_BASE}/products/index", json=payload, headers=_headers()
        )
        resp.raise_for_status()
        data = resp.json()
    if not data.get("isSuccess"):
        raise RuntimeError(f"dropi products/index failed: status={data.get('status')}")
    return data.get("objects") or []


async def list_categories() -> list[dict]:
    """Categorías del catálogo: [{id, name}]."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.DROPI_API_BASE}/categories/", headers=_headers())
        resp.raise_for_status()
        data = resp.json()
    if not data.get("isSuccess"):
        raise RuntimeError("dropi categories failed")
    return data.get("objects") or []


async def get_product_detail(product_id: int) -> dict:
    """Detalle completo de un producto (products/v2): descripción, fotos, user_id."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{settings.DROPI_API_BASE}/products/v2/{product_id}", headers=_headers()
        )
        resp.raise_for_status()
        data = resp.json()
    if not data.get("isSuccess"):
        raise RuntimeError(f"dropi products/v2/{product_id} failed")
    obj = data.get("objects")
    if isinstance(obj, list):
        obj = obj[0] if obj else None
    if not obj:
        raise RuntimeError(f"dropi product {product_id} sin datos")
    return obj


async def list_orders(result_number: int | None = None) -> list[dict]:
    """Pedidos de la integración WOOCOMERCE (GET /orders/myorders, feature 016).

    Usa el token de la integración WOOCOMERCE (no el de Scout). El parámetro que
    devuelve datos es `result_number` (no `pageSize`, validado en vivo R1). Las
    órdenes traen `shop_order_id` = ID de la orden en WooCommerce (None si la orden
    fue creada directo en Dropi y no tiene contraparte en la tienda).
    """
    # Dropi rechaza result_number alto con HTTP 400 (validado: 100 ok, 200 falla).
    n = min(result_number or settings.DROPI_ORDERS_FETCH, 100)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{settings.DROPI_API_BASE}/orders/myorders",
            params={"result_number": n},
            headers=_headers(settings.DROPI_WC_INTEGRATION_KEY),
        )
        resp.raise_for_status()
        data = resp.json()
    if not data.get("isSuccess"):
        raise RuntimeError(f"dropi orders/myorders failed: status={data.get('status')}")
    return data.get("objects") or []


def order_sync_fields(o: dict) -> dict:
    """Extrae los campos relevantes de una orden Dropi para sincronizar con WC.

    `wc_order_id` es la clave de cruce contra la orden de WooCommerce.
    """
    dc = o.get("distribution_company") or {}
    return {
        "dropi_order_id": o.get("id"),
        "wc_order_id": o.get("shop_order_id"),
        "status": (o.get("status") or "").strip() or None,
        "carrier": dc.get("name") or o.get("shipping_company"),
        "guide": o.get("shipping_guide") or None,
        "guide_url": o.get("guia_urls3") or None,
        "total": o.get("total_order"),
        "updated_at": o.get("updated_at"),
    }


def image_urls(product: dict) -> list[str]:
    """URLs absolutas de las fotos del producto (gallery/photos con urlS3)."""
    from urllib.parse import quote

    base = settings.DROPI_API_BASE.split("/integrations")[0] + "/"
    urls = []
    for ph in product.get("photos") or product.get("gallery") or []:
        u = ph.get("url")
        if not u and ph.get("urlS3"):
            u = base + quote(ph["urlS3"], safe="/:")
        if u:
            urls.append(u)
    return urls


def stock_total(product: dict) -> int:
    """Suma el stock de todas las bodegas del producto."""
    return sum(int(w.get("stock") or 0) for w in product.get("warehouse_product") or [])


def first_category(product: dict) -> str | None:
    cats = product.get("categories") or []
    return cats[0].get("name") if cats else None
