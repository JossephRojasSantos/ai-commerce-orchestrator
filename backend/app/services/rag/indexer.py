from __future__ import annotations

import structlog

from app.clients.embeddings import embed_texts
from app.services.rag.vector_store import get_vector_store

logger = structlog.get_logger()


def _product_to_text(p: dict) -> str:
    parts = [p.get("name", ""), p.get("short_description", ""), p.get("description", "")]
    cats = " ".join(c["name"] for c in p.get("categories", []))
    tags = " ".join(t["name"] for t in p.get("tags", []))
    return " ".join(filter(None, [*parts, cats, tags]))


def _product_to_payload(p: dict) -> dict:
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


async def index_product(payload: dict) -> None:
    wc_id = payload.get("id")
    if not wc_id:
        logger.warning("indexer_missing_id", payload_keys=list(payload.keys()))
        return
    text = _product_to_text(payload)
    vectors = await embed_texts([text])
    store = await get_vector_store()
    await store.upsert(
        [
            {
                "id": wc_id,
                "vector": vectors[0],
                "payload": _product_to_payload(payload),
            }
        ]
    )
    logger.info("indexer_product_upserted", wc_id=wc_id)


async def delete_product(wc_id: int) -> None:
    store = await get_vector_store()
    await store.delete([wc_id])
    logger.info("indexer_product_deleted", wc_id=wc_id)
