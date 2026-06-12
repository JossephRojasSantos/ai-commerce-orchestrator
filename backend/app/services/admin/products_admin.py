"""Productos administrables: origen, costo del proveedor y margen (feature 012).

El costo Dropi vive en el meta `_dropi_product` (objeto PHP serializado por el
plugin Dropify); se extrae `sale_price` con regex (research R2). El meta crudo
JAMÁS sale de este módulo — contiene el token JWT de la integración Dropi.
"""

import re

import structlog

from app.clients.woocommerce import get_wc_client
from app.config import settings
from app.core.cache import cache_delete, cache_get, cache_set

logger = structlog.get_logger()

_SALE_PRICE_RE = re.compile(r's:10:"sale_price";s:\d+:"([\d.]+)"')
_CACHE_KEY = "admin:products"
_CACHE_TTL = 60


def _extract_supplier_cost(meta_data: list) -> float | None:
    for meta in meta_data or []:
        if meta.get("key") == "_dropi_product":
            m = _SALE_PRICE_RE.search(str(meta.get("value", "")))
            if m:
                return float(m.group(1))
    return None


def _is_dropi(meta_data: list) -> bool:
    return any(m.get("key") == "_dropi_product_id" for m in meta_data or [])


def _to_dto(p: dict) -> dict:
    meta = p.get("meta_data", [])
    origin = "dropi" if _is_dropi(meta) else "own"
    supplier_cost = _extract_supplier_cost(meta) if origin == "dropi" else None
    price = float(p.get("price") or 0)

    margin = None
    margin_alert = False
    if supplier_cost is not None:
        margin = price - supplier_cost - settings.ADMIN_SHIPPING_COST_ESTIMATE
        margin_alert = margin <= 0

    image = ""
    if p.get("images"):
        image = p["images"][0].get("src", "")

    return {
        "id": p["id"],
        "name": p.get("name", ""),
        "image": image,
        "price": price,
        "regular_price": float(p.get("regular_price") or 0),
        "stock": p.get("stock_quantity"),
        "stock_status": p.get("stock_status", ""),
        "status": p.get("status", ""),
        "origin": origin,
        "supplier_cost": supplier_cost,
        "margin": margin,
        "margin_alert": margin_alert,
    }


async def list_products() -> list[dict]:
    cached = await cache_get(_CACHE_KEY)
    if cached is not None:
        return cached
    wc = await get_wc_client()
    raw = await wc.list_products_raw()
    items = [_to_dto(p) for p in raw]
    await cache_set(_CACHE_KEY, items, _CACHE_TTL)
    return items


async def update_product(product_id: int, price: float | None, stock: int | None) -> dict:
    payload: dict = {}
    if price is not None:
        payload["regular_price"] = str(int(price))
    if stock is not None:
        payload["stock_quantity"] = stock
        payload["manage_stock"] = True

    wc = await get_wc_client()
    updated = await wc.update_product(product_id, payload)
    await invalidate_caches()
    logger.info("admin.product_updated", product_id=product_id, fields=list(payload))
    return _to_dto(updated)


async def invalidate_caches() -> None:
    await cache_delete(_CACHE_KEY)
    for period in ("today", "7d", "30d"):
        await cache_delete(f"admin:stats:{period}")
    await cache_delete("admin:customers")


def supplier_cost_map(products: list[dict]) -> dict[int, float]:
    """product_id → costo proveedor, para el cálculo de ganancia en stats."""
    return {p["id"]: p["supplier_cost"] for p in products if p.get("supplier_cost") is not None}


__all__ = ["list_products", "update_product", "invalidate_caches", "supplier_cost_map"]
