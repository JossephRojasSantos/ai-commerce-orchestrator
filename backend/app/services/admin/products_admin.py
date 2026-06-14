"""Productos administrables: origen, costo del proveedor y margen (feature 012).

El costo Dropi vive en el meta `_dropi_product` (objeto PHP serializado por el
plugin Dropify); se extrae `sale_price` con regex (research R2). El meta crudo
JAMÁS sale de este módulo — contiene el token JWT de la integración Dropi.
"""

import json
import re

import structlog

from app.clients.woocommerce import get_wc_client
from app.config import settings
from app.core.cache import cache_delete, cache_get, cache_set

logger = structlog.get_logger()

_SALE_PRICE_RE = re.compile(r's:10:"sale_price";s:\d+:"([\d.]+)"')
_LANDING_META = "_tm_landing"  # config de la landing por cajas (feature 019)
_CACHE_KEY = "admin:products"
_CACHE_TTL = 60


# Contenido editable de las secciones del producto (feature 019).
# clave del DTO → meta WordPress (_tm_*). El template los lee con tm_get_parity_meta().
_TM_META = {
    "benefits": "_tm_benefits",  # lista de strings
    "includes": "_tm_includes",
    "warranty": "_tm_warranty",
    "use_case": "_tm_use_case",
    "size": "_tm_size",
    "badge": "_tm_badge",
    "rating": "_tm_rating",
    "reviews": "_tm_reviews",
}


def _extract_tm_meta(meta_data: list) -> dict:
    raw = {m.get("key"): m.get("value") for m in meta_data or []}
    out = {}
    for k, meta_key in _TM_META.items():
        v = raw.get(meta_key)
        if k == "benefits":
            out[k] = v if isinstance(v, list) else []
        else:
            out[k] = v if v not in (None, False) else ""
    return out


def _extract_landing(meta_data: list) -> dict:
    for meta in meta_data or []:
        if meta.get("key") == _LANDING_META:
            try:
                v = meta.get("value")
                return json.loads(v) if isinstance(v, str) else (v or {})
            except (ValueError, TypeError):
                return {}
    return {}


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
    price_floor = None
    if supplier_cost is not None:
        margin = price - supplier_cost - settings.ADMIN_SHIPPING_COST_ESTIMATE
        # Piso de precio = costo + flete + margen mínimo. Vender por debajo → Dropi
        # rechaza el pedido COD ("monto a ganar ≤ 0").
        price_floor = round(
            supplier_cost + settings.ADMIN_SHIPPING_COST_ESTIMATE + settings.ADMIN_MIN_MARGIN
        )
        margin_alert = price < price_floor

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
        "price_floor": price_floor,
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


def _to_detail(p: dict) -> dict:
    """DTO de edición — incluye descripción e imágenes (sin meta crudo)."""
    dto = _to_dto(p)
    dto["description"] = p.get("description", "")
    dto["short_description"] = p.get("short_description", "")
    dto["images"] = [
        {"id": img.get("id"), "src": img.get("src", "")} for img in p.get("images") or []
    ]
    dto["permalink"] = p.get("permalink", "")
    dto["visible"] = p.get("status") == "publish"
    dto["landing"] = _extract_landing(p.get("meta_data", []))
    dto["tm_meta"] = _extract_tm_meta(p.get("meta_data", []))
    return dto


async def get_product_detail(product_id: int) -> dict:
    wc = await get_wc_client()
    raw = await wc.get_product_raw(product_id)
    return _to_detail(raw)


async def update_product(
    product_id: int,
    price: float | None = None,
    stock: int | None = None,
    name: str | None = None,
    description: str | None = None,
    short_description: str | None = None,
    visible: bool | None = None,
    landing: dict | None = None,
    tm_meta: dict | None = None,
) -> dict:
    payload: dict = {}
    meta: list = []
    if landing is not None:
        meta.append({"key": _LANDING_META, "value": json.dumps(landing, ensure_ascii=False)})
    if tm_meta is not None:
        for k, meta_key in _TM_META.items():
            if k not in tm_meta:
                continue
            v = tm_meta[k]
            if k == "benefits":
                v = [str(x).strip() for x in (v or []) if str(x).strip()]
            elif k in ("rating", "reviews"):
                v = v if v not in (None, "") else 0
            meta.append({"key": meta_key, "value": v})
    if meta:
        payload["meta_data"] = meta
    if price is not None:
        payload["regular_price"] = str(int(price))
    if stock is not None:
        payload["stock_quantity"] = stock
        payload["manage_stock"] = True
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if short_description is not None:
        payload["short_description"] = short_description
    if visible is not None:
        # publish = visible en la tienda · draft = oculto
        payload["status"] = "publish" if visible else "draft"
        payload["catalog_visibility"] = "visible" if visible else "hidden"

    wc = await get_wc_client()
    updated = await wc.update_product(product_id, payload)
    await invalidate_caches()
    logger.info("admin.product_updated", product_id=product_id, fields=list(payload))
    return _to_detail(updated)


async def add_product_image(product_id: int, content: bytes, mime: str) -> dict:
    """Sube un creativo: lo guarda temporal, lo añade vía URL y WC lo descarga.

    Conserva las imágenes existentes (por id) y agrega la nueva (por src).
    """
    from app.services.admin import media_store

    wc = await get_wc_client()
    current = await wc.get_product_raw(product_id)
    existing = [{"id": img["id"]} for img in current.get("images") or [] if img.get("id")]

    media_id = await media_store.store_image(content, mime)
    images = existing + [{"src": media_store.public_url(media_id)}]

    updated = await wc.update_product(product_id, {"images": images})
    await invalidate_caches()
    logger.info("admin.product_image_added", product_id=product_id)
    return _to_detail(updated)


async def delete_product_image(product_id: int, image_id: int) -> dict:
    """Quita una imagen del producto (deja las demás)."""
    wc = await get_wc_client()
    current = await wc.get_product_raw(product_id)
    images = [{"id": img["id"]} for img in current.get("images") or [] if img.get("id") != image_id]
    updated = await wc.update_product(product_id, {"images": images})
    await invalidate_caches()
    logger.info("admin.product_image_deleted", product_id=product_id, image_id=image_id)
    return _to_detail(updated)


async def invalidate_caches() -> None:
    await cache_delete(_CACHE_KEY)
    for period in ("today", "7d", "30d"):
        await cache_delete(f"admin:stats:{period}")
    await cache_delete("admin:customers")


def supplier_cost_map(products: list[dict]) -> dict[int, float]:
    """product_id → costo proveedor, para el cálculo de ganancia en stats."""
    return {p["id"]: p["supplier_cost"] for p in products if p.get("supplier_cost") is not None}


__all__ = [
    "list_products",
    "get_product_detail",
    "update_product",
    "add_product_image",
    "delete_product_image",
    "invalidate_caches",
    "supplier_cost_map",
]
