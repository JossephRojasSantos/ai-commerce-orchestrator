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


def _headers() -> dict:
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": settings.DROPI_USER_AGENT,
        "dropi-integration-key": settings.DROPI_INTEGRATION_KEY,
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


def stock_total(product: dict) -> int:
    """Suma el stock de todas las bodegas del producto."""
    return sum(int(w.get("stock") or 0) for w in product.get("warehouse_product") or [])


def first_category(product: dict) -> str | None:
    cats = product.get("categories") or []
    return cats[0].get("name") if cats else None
