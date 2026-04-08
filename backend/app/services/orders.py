import structlog
from fastapi import HTTPException

from app.clients.woocommerce import WCClientError, WCServerError, get_wc_client
from app.config import settings
from app.core.cache import cache_get, cache_set
from app.core.retry import wc_retry
from app.schemas.woocommerce import WCOrder

logger = structlog.get_logger()


@wc_retry
async def _fetch_order(order_id: int) -> dict:
    client = await get_wc_client()
    return await client._get(f"/orders/{order_id}")


@wc_retry
async def _fetch_orders_by_customer(customer_id: int, status: str | None) -> list[dict]:
    client = await get_wc_client()
    params: dict = {"customer": customer_id}
    if status:
        params["status"] = status
    return await client._get("/orders", params)


async def get_order(order_id: int) -> WCOrder:
    cache_key = f"wc:orders:{order_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return WCOrder.model_validate(cached)
    try:
        data = await _fetch_order(order_id)
    except WCClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="resource_not_found") from e
        raise HTTPException(status_code=e.status_code, detail="wc_client_error") from e
    except WCServerError as e:
        raise HTTPException(status_code=503, detail="wc_unavailable") from e
    await cache_set(cache_key, data, settings.WC_CACHE_TTL_ORDERS)
    return WCOrder.model_validate(data)


async def list_orders_by_customer(customer_id: int, status: str | None = None) -> list[WCOrder]:
    status_key = status or "all"
    cache_key = f"wc:orders:customer:{customer_id}:{status_key}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return [WCOrder.model_validate(o) for o in cached]
    try:
        data = await _fetch_orders_by_customer(customer_id, status)
    except WCClientError as e:
        raise HTTPException(status_code=e.status_code, detail="wc_client_error") from e
    except WCServerError as e:
        raise HTTPException(status_code=503, detail="wc_unavailable") from e
    await cache_set(cache_key, data, settings.WC_CACHE_TTL_ORDERS)
    return [WCOrder.model_validate(o) for o in data]
