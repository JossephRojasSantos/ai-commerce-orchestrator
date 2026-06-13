"""Ingesta del catálogo Dropi a snapshots diarios (feature 014, FR-001/002/015).

Ejecutable: `python -m app.workers.scout_ingest` (cron VPS 02:00) o invocado en
background desde POST /v1/admin/scout/ingest. Lock Redis contra concurrencia (FR-016).
"""

import asyncio
from datetime import UTC, datetime

import structlog

from app.clients import dropi
from app.config import settings
from app.models.scout import ScoutIngestRun

logger = structlog.get_logger()

INGEST_LOCK_KEY = "scout:ingest_lock"
LOCK_TTL = 3600  # 1h — cubre SC-001 (< 30 min) con margen


async def run_ingest() -> dict:
    """Recorre el catálogo paginado, upserta snapshots del día y recalcula señales.

    Una falla parcial marca el run como error pero no toca días anteriores (FR-015):
    los snapshots ya upsertados del día quedan, el histórico es inmutable.
    """
    from app.db.base import AsyncSessionLocal
    from app.services.admin.scout import business_today, compute_signals, upsert_snapshot

    if not settings.DROPI_INTEGRATION_KEY:
        logger.warning("scout.ingest_skipped", reason="DROPI_INTEGRATION_KEY vacío")
        return {"status": "skipped", "processed": 0, "failed": 0}

    today = business_today()
    processed = failed = 0
    seen: set[int] = set()

    async with AsyncSessionLocal() as db:
        run = ScoutIngestRun(kind="ingest", status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    status, error_msg = "ok", None
    try:
        async with AsyncSessionLocal() as db:
            start = 0
            while True:
                batch = await dropi.list_products(start)
                if not batch:
                    break
                for product in batch:
                    pid = int(product.get("id") or 0)
                    if not pid or pid in seen:  # dedup entre páginas
                        continue
                    seen.add(pid)
                    try:
                        await upsert_snapshot(db, product, today)
                        processed += 1
                    except Exception as exc:  # noqa: BLE001 — un producto no tumba la ingesta
                        failed += 1
                        logger.warning("scout.product_failed", pid=pid, error=str(exc))
                await db.commit()
                start += dropi.PAGE_SIZE
            signals = await compute_signals(db)
            logger.info("scout.ingest_done", processed=processed, failed=failed, signals=signals)
    except Exception as exc:  # noqa: BLE001
        status, error_msg = "error", str(exc)[:500]
        logger.error("scout.ingest_failed", error=str(exc))

    async with AsyncSessionLocal() as db:
        run = await db.get(ScoutIngestRun, run_id)
        run.status = status
        run.processed = processed
        run.failed = failed
        run.error = error_msg
        run.finished_at = datetime.now(UTC)
        await db.commit()

    return {"status": status, "processed": processed, "failed": failed, "run_id": run_id}


async def run_ingest_locked() -> dict | None:
    """Variante con lock Redis; None si ya hay una ingesta corriendo (FR-016)."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        acquired = await r.set(INGEST_LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
        if not acquired:
            return None
        try:
            return await run_ingest()
        finally:
            await r.delete(INGEST_LOCK_KEY)
    finally:
        await r.aclose()


if __name__ == "__main__":
    result = asyncio.run(run_ingest_locked())
    print(result if result is not None else {"status": "already_running"})
