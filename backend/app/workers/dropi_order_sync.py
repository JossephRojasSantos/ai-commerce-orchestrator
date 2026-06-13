"""Worker de sincronización de pedidos Dropi → WooCommerce (feature 016).

Ejecutable: `python -m app.workers.dropi_order_sync` (cron VPS) o invocado en
background desde POST /v1/admin/orders/sync. Lock Redis contra concurrencia.
"""

import asyncio

import structlog

from app.config import settings
from app.services.admin.order_sync import sync_orders

logger = structlog.get_logger()

SYNC_LOCK_KEY = "order_sync:lock"
LOCK_TTL = 1800  # 30 min, margen amplio sobre la duración real


async def run_sync_locked() -> dict | None:
    """Variante con lock Redis; None si ya hay un sync corriendo."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        acquired = await r.set(SYNC_LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
        if not acquired:
            return None
        try:
            return await sync_orders()
        finally:
            await r.delete(SYNC_LOCK_KEY)
    finally:
        await r.aclose()


if __name__ == "__main__":
    result = asyncio.run(run_sync_locked())
    print(result if result is not None else {"status": "already_running"})
