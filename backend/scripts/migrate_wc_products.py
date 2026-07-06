#!/usr/bin/env python
"""
Migra productos WooCommerce → tabla store_product (fase 2 migración headless).

Re-ejecutable: upsert por wc_product_id. Copia precio, descripción, galería,
metas _tm_* (feature 019: reviews, faq…), landing y datos Dropi (product_id,
supplier_id, costo). WordPress sigue siendo editable hasta el cutover; correr
de nuevo sincroniza cambios.

Usage:
    python scripts/migrate_wc_products.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from app.clients.woocommerce import get_wc_client
from app.services.admin.products_admin import (
    _extract_landing,
    _extract_supplier_cost,
    _extract_tm_meta,
)

logger = structlog.get_logger()

_DROPI_ID_KEY = "_dropi_product_id"
_SUPPLIER_ID_RE = re.compile(r's:7:"user_id";(?:s:\d+:"(\d+)"|i:(\d+))')

# La media de productos se sirve desde Oracle (nginx /media/), no desde WP, para
# que las imágenes sobrevivan al apagado de WordPress. Reescribir al migrar evita
# que un re-run devuelva las URLs a tiendamagica.shop.
_WP_UPLOADS = "https://tiendamagica.shop/wp-content/uploads/"
_MEDIA_BASE = "https://api.tiendamagica.shop/media/"


def _rewrite_media(src: str) -> str:
    return src.replace(_WP_UPLOADS, _MEDIA_BASE) if src else src


def _meta(meta_data: list, key: str):
    for m in meta_data or []:
        if m.get("key") == key:
            return m.get("value")
    return None


def _extract_supplier_id(meta_data: list) -> int | None:
    m = _SUPPLIER_ID_RE.search(str(_meta(meta_data, "_dropi_product") or ""))
    if m:
        return int(m.group(1) or m.group(2))
    return None


def _to_row(p: dict) -> dict:
    meta = p.get("meta_data", [])
    tm = _extract_tm_meta(meta)
    dropi_id = _meta(meta, _DROPI_ID_KEY)
    content = {
        **tm,
        "landing": _extract_landing(meta),
    }
    regular = float(p.get("regular_price") or 0)
    price = float(p.get("price") or 0)
    return {
        "wc_product_id": p["id"],
        "slug": p.get("slug") or f"producto-{p['id']}",
        "name": p.get("name", ""),
        "price": price,
        # precio ancla = regular_price cuando hay oferta activa
        "anchor_price": regular if regular > price else None,
        "description": p.get("description", ""),
        "short_description": p.get("short_description", ""),
        "dropi_product_id": int(dropi_id) if dropi_id else None,
        "dropi_supplier_id": _extract_supplier_id(meta),
        "supplier_cost": _extract_supplier_cost(meta),
        "images": [_rewrite_media(img.get("src", "")) for img in p.get("images") or []],
        "content": content,
        "active": p.get("status") == "publish",
    }


async def run(dry_run: bool) -> None:
    wc = await get_wc_client()
    raw = await wc.list_products_raw()
    rows = [_to_row(p) for p in raw]
    logger.info("productos WC leídos", total=len(rows))

    if dry_run:
        for r in rows:
            logger.info(
                "dry-run",
                slug=r["slug"],
                price=r["price"],
                dropi_id=r["dropi_product_id"],
                supplier=r["dropi_supplier_id"],
                active=r["active"],
                reviews=len(r["content"].get("reviews") or []),
            )
        return

    # Imports diferidos: el dry-run funciona sin la migración store_tables aplicada
    from app.db.base import AsyncSessionLocal
    from app.models.store import StoreProduct
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    async with AsyncSessionLocal() as db:
        for r in rows:
            stmt = pg_insert(StoreProduct).values(**r)
            update_cols = {k: stmt.excluded[k] for k in r if k != "wc_product_id"}
            await db.execute(
                stmt.on_conflict_do_update(index_elements=["wc_product_id"], set_=update_cols)
            )
        await db.commit()
    logger.info("migración completada", upserted=len(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
