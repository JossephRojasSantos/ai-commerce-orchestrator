import hashlib
import json

import structlog
from fastapi import HTTPException

from app.clients.woocommerce import WCClientError, WCServerError, get_wc_client
from app.config import settings
from app.core.cache import cache_get, cache_set
from app.core.retry import wc_retry
from app.schemas.woocommerce import WCProduct

logger = structlog.get_logger()


@wc_retry
async def _fetch_products(params: dict) -> list[dict]:
    client = await get_wc_client()
    return await client._get("/products", params)


@wc_retry
async def _fetch_product(product_id: int) -> dict:
    client = await get_wc_client()
    return await client._get(f"/products/{product_id}")


async def list_products(
    page: int = 1,
    per_page: int = 10,
    search: str = "",
    category: str = "",
) -> list[WCProduct]:
    params = {"page": page, "per_page": per_page}
    if search:
        params["search"] = search
    if category:
        params["category"] = category
    cache_key = (
        "wc:products:list:" + hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        return [WCProduct.model_validate(p) for p in cached]
    try:
        data = await _fetch_products(params)
    except WCClientError as e:
        raise HTTPException(status_code=e.status_code, detail="wc_client_error") from e
    except WCServerError as e:
        raise HTTPException(status_code=503, detail="wc_unavailable") from e
    await cache_set(cache_key, data, settings.WC_CACHE_TTL_PRODUCTS)
    return [WCProduct.model_validate(p) for p in data]


async def get_product(product_id: int) -> WCProduct:
    cache_key = f"wc:products:{product_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return WCProduct.model_validate(cached)
    try:
        data = await _fetch_product(product_id)
    except WCClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="resource_not_found") from e
        raise HTTPException(status_code=e.status_code, detail="wc_client_error") from e
    except WCServerError as e:
        raise HTTPException(status_code=503, detail="wc_unavailable") from e
    await cache_set(cache_key, data, settings.WC_CACHE_TTL_PRODUCTS)
    return WCProduct.model_validate(data)
