from datetime import datetime, UTC

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas.health import DependencyStatus, HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/ready", response_model=DependencyStatus)
async def readiness():
    db_ok = True
    redis_ok = True

    # Check DB
    try:
        import asyncpg

        parsed = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(parsed)
        await conn.execute("SELECT 1")
        await conn.close()
    except Exception:
        db_ok = False

    # Check Redis
    try:
        from redis.asyncio import Redis

        r = Redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_ok = False

    status = "ok" if (db_ok and redis_ok) else "degraded"
    payload = DependencyStatus(status=status, db=db_ok, redis=redis_ok)

    if status == "degraded":
        return JSONResponse(status_code=503, content=payload.model_dump())

    return payload
