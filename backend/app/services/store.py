"""Tienda headless — catálogo read-only y copia de órdenes (fase 2 migración WP).

DTOs alineados con el frontend Next.js (`tienda-next/lib/store-api.ts`).
Cache Redis corta: el frontend además cachea vía ISR, esto solo amortigua ráfagas.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete, cache_get, cache_set
from app.models.store import StoreOrder, StoreProduct

logger = structlog.get_logger()

_CACHE_LIST = "store:products"
_CACHE_TTL = 120


def _to_dto(p: StoreProduct) -> dict:
    content = p.content or {}
    return {
        "slug": p.slug,
        "nombre": p.name,
        "precioVenta": float(p.price),
        "precioAncla": float(p.anchor_price) if p.anchor_price is not None else None,
        "dropiId": p.dropi_product_id,
        "supplierId": p.dropi_supplier_id,
        "descripcion": p.description,
        "descripcionCorta": p.short_description,
        "galeria": p.images or [],
        "resenas": content.get("reviews") or [],
        "faq": content.get("faq") or [],
        "comparativa": content.get("comparativa"),
        "escasez": content.get("escasez"),
        "contenido": content,  # resto de secciones editables (benefits, landing…)
    }


async def list_products(db: AsyncSession) -> list[dict]:
    cached = await cache_get(_CACHE_LIST)
    if cached is not None:
        return cached
    rows = (
        (
            await db.execute(
                select(StoreProduct).where(StoreProduct.active).order_by(StoreProduct.id)
            )
        )
        .scalars()
        .all()
    )
    items = [_to_dto(p) for p in rows]
    await cache_set(_CACHE_LIST, items, _CACHE_TTL)
    return items


async def get_product(db: AsyncSession, slug: str) -> dict | None:
    row = (
        await db.execute(select(StoreProduct).where(StoreProduct.slug == slug, StoreProduct.active))
    ).scalar_one_or_none()
    return _to_dto(row) if row else None


async def invalidate_cache() -> None:
    await cache_delete(_CACHE_LIST)


async def save_order(db: AsyncSession, payload: dict) -> int:
    """Upsert idempotente por shop_order_id (el frontend puede reintentar)."""
    dropi = payload.get("dropi") or {}
    dropi_order = dropi.get("order") if isinstance(dropi.get("order"), dict) else {}
    stmt = (
        pg_insert(StoreOrder)
        .values(
            shop_order_id=str(payload["shopOrderId"]),
            dropi_order_id=dropi_order.get("id"),
            total=payload.get("total") or 0,
            customer=payload.get("cliente") or {},
            products=payload.get("productos") or [],
            dropi_payload=dropi,
        )
        .on_conflict_do_nothing(index_elements=["shop_order_id"])
        .returning(StoreOrder.id)
    )
    result = await db.execute(stmt)
    await db.commit()
    row = result.scalar_one_or_none()
    if row is None:
        logger.info(
            "store_order duplicada (reintento frontend)", shop_order_id=payload["shopOrderId"]
        )
        existing = (
            await db.execute(
                select(StoreOrder.id).where(StoreOrder.shop_order_id == str(payload["shopOrderId"]))
            )
        ).scalar_one()
        return existing
    return row
