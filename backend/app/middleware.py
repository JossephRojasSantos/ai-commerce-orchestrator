import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.core.cache import get_redis

try:
    from app.core.metrics import (
        http_errors_total,
        http_request_duration_seconds,
        http_requests_total,
    )

    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

log = structlog.get_logger()

_RATE_LIMIT_SKIP = ("/health", "/metrics", "/api/whatsapp/webhook")


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    """Block IPs exceeding IP_RATE_LIMIT_PER_MIN requests per minute."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith(_RATE_LIMIT_SKIP):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        try:
            redis = get_redis()
            key = f"ratelimit:ip:{ip}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
            if count > settings.IP_RATE_LIMIT_PER_MIN:
                log.warning("ip.rate_limited", ip=ip, count=count)
                return JSONResponse(status_code=429, content={"detail": "rate_limit_exceeded"})
        except Exception:
            log.warning("ip.ratelimit.redis_unavailable", ip=ip)

        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = trace_id
        request.state.trace_id = trace_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        t0 = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)

        status = response.status_code
        method = request.method
        path = request.url.path

        log.info(
            "request",
            method=method,
            path=path,
            status=status,
            duration_ms=duration_ms,
            trace_id=trace_id,
        )

        if _METRICS_AVAILABLE:
            try:
                http_requests_total.labels(method=method, path=path, status=str(status)).inc()
                http_request_duration_seconds.labels(method=method, path=path).observe(
                    duration_ms / 1000
                )
                if status >= 400:
                    http_errors_total.labels(method=method, path=path, status=str(status)).inc()
            except Exception:
                pass

        response.headers["X-Request-ID"] = trace_id
        return response


def setup_logging(settings) -> None:
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.APP_ENV == "production":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
