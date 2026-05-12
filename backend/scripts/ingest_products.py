#!/usr/bin/env python
"""
Ingest WooCommerce products into Qdrant vector store.

Usage:
    python scripts/ingest_products.py [--page-size N] [--max-pages N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

# Allow running from repo root without installing package
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from app.clients.embeddings import embed_texts
from app.clients.woocommerce import WooCommerceClient
from app.config import settings
from app.services.rag.vector_store import get_vector_store

logger = structlog.get_logger()


def product_to_text(p: dict) -> str:
    parts = [p.get("name", ""), p.get("short_description", ""), p.get("description", "")]
    cats = " ".join(c["name"] for c in p.get("categories", []))
    tags = " ".join(t["name"] for t in p.get("tags", []))
    return " ".join(filter(None, [*parts, cats, tags]))


def product_id_to_point_id(wc_id: int) -> int:
    return wc_id


def product_to_payload(p: dict) -> dict:
    return {
        "wc_id": p["id"],
        "name": p.get("name", ""),
        "slug": p.get("slug", ""),
        "price": p.get("price", ""),
        "regular_price": p.get("regular_price", ""),
        "sale_price": p.get("sale_price", ""),
        "status": p.get("status", ""),
        "stock_status": p.get("stock_status", ""),
        "categories": [c["name"] for c in p.get("categories", [])],
        "tags": [t["name"] for t in p.get("tags", [])],
        "permalink": p.get("permalink", ""),
        "image": (p.get("images") or [{}])[0].get("src", ""),
        "short_description": p.get("short_description", ""),
    }


async def ingest(page_size: int, max_pages: int | None, dry_run: bool) -> None:
    store = await get_vector_store()
    logger.info("ingest_start", collection=settings.QDRANT_COLLECTION, dry_run=dry_run)

    total = 0
    async with WooCommerceClient() as wc:
        page = 1
        while True:
            products = await wc._get(
                "/products",
                params={"per_page": page_size, "page": page, "status": "publish"},
            )
            if not products:
                break

            texts = [product_to_text(p) for p in products]
            vectors = await embed_texts(texts)

            points = [
                {
                    "id": product_id_to_point_id(p["id"]),
                    "vector": vec,
                    "payload": product_to_payload(p),
                }
                for p, vec in zip(products, vectors)
            ]

            if not dry_run:
                await store.upsert(points)

            total += len(products)
            logger.info("ingest_batch", page=page, count=len(products), total=total)

            if len(products) < page_size:
                break
            if max_pages and page >= max_pages:
                break
            page += 1

    logger.info("ingest_done", total=total, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest WC products into Qdrant")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(ingest(args.page_size, args.max_pages, args.dry_run))


if __name__ == "__main__":
    main()
