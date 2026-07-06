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


def _as_list(v) -> list:
    return v if isinstance(v, list) else []


def _to_dto(p: StoreProduct) -> dict:
    """Mapea contenido WP (metas _tm_* + _tm_landing) al DTO del frontend.

    Ojo: `content["reviews"]` (meta _tm_reviews) es el CONTADOR mostrado en la
    tarjeta ("210 reseñas"); las reseñas reales editables del panel viven en
    `content["landing"]["reviews"]` con formato {name, city, stars, text, image}
    (feature 019, ver tm-landing.php). FAQ usa {q, a}; escasez `scarcity_units`.
    """
    content = p.content or {}
    landing = content.get("landing")
    if not isinstance(landing, dict):
        landing = {}

    resenas = [
        {
            "autor": f"{r.get('name') or 'Cliente verificado'} — {r.get('city') or 'Colombia'}",
            "estrellas": max(1, min(5, int(r.get("stars") or 5))),
            "texto": r["text"],
            "foto": r.get("image") or None,
        }
        for r in _as_list(landing.get("reviews"))
        if isinstance(r, dict) and r.get("text")
    ]
    faq = [
        {"pregunta": f.get("q") or "", "respuesta": f.get("a") or ""}
        for f in _as_list(landing.get("faq"))
        if isinstance(f, dict) and f.get("q")
    ]
    try:
        scarcity = int(landing.get("scarcity_units") or 0)
    except (TypeError, ValueError):
        scarcity = 0

    # Precio ancla: price_old de la landing manda; si no, el regular_price migrado
    try:
        price_old = float(landing.get("price_old") or 0)
    except (TypeError, ValueError):
        price_old = 0
    anchor = p.anchor_price if p.anchor_price is not None else None
    if price_old > float(p.price):
        anchor = price_old

    return {
        "slug": p.slug,
        "nombre": p.name,
        "precioVenta": float(p.price),
        "precioAncla": float(anchor) if anchor is not None else None,
        "dropiId": p.dropi_product_id,
        "supplierId": p.dropi_supplier_id,
        "descripcion": p.description,
        "descripcionCorta": p.short_description,
        "galeria": _as_list(p.images),
        "resenas": resenas,
        "faq": faq,
        "comparativa": _as_list(landing.get("compare")) or None,
        "escasez": (
            {"activa": True, "mensaje": f"¡Quedan solo {scarcity} unidades!"}
            if scarcity > 0
            else None
        ),
        "contenido": content,  # resto de secciones editables (benefits, rating, landing…)
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
