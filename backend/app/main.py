import asyncio
import contextlib
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.middleware import IPRateLimitMiddleware, RequestIDMiddleware, setup_logging
from app.routers.health import router as health_router
from app.schemas.errors import ErrorResponse

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.workers.whatsapp_consumer import run_consumer

    stop_event = asyncio.Event()
    task = asyncio.create_task(run_consumer(stop_event))
    yield
    stop_event.set()
    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=10)


def create_app() -> FastAPI:
    setup_logging(settings)

    app = FastAPI(
        title="AI Commerce Orchestrator",
        version=settings.APP_VERSION,
        description="Backend base para agentes IA de comercio electrónico",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(IPRateLimitMiddleware)

    app.include_router(health_router)

    from app.routers.orders import router as orders_router
    from app.routers.products import router as products_router

    app.include_router(products_router)
    app.include_router(orders_router)

    from app.routers.chat import router as chat_router

    app.include_router(chat_router)

    if settings.METRICS_ENABLED:
        from app.routers.metrics import router as metrics_router

        app.include_router(metrics_router)

    from app.routers.orchestrator import router as orchestrator_router
    from app.routers.whatsapp import router as whatsapp_router

    app.include_router(orchestrator_router)
    app.include_router(whatsapp_router)

    register_exception_handlers(app)
    return app


def register_exception_handlers(app: FastAPI) -> None:
    from app.clients.woocommerce import WCClientError, WCServerError

    @app.exception_handler(WCServerError)
    async def wc_server_error_handler(request: Request, exc: WCServerError):
        request_id = getattr(request.state, "request_id", "")
        logger.error(
            "wc_server_error",
            status_code=exc.status_code,
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )
        error = ErrorResponse(
            code="wc_unavailable", message="WooCommerce service unavailable", request_id=request_id
        )
        return JSONResponse(status_code=503, content=error.model_dump())

    @app.exception_handler(WCClientError)
    async def wc_client_error_handler(request: Request, exc: WCClientError):
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            "wc_client_error",
            status_code=exc.status_code,
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )
        error = ErrorResponse(code="wc_client_error", message=exc.message, request_id=request_id)
        return JSONResponse(status_code=422, content=error.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            "http_error",
            status_code=exc.status_code,
            detail=exc.detail,
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )
        error = ErrorResponse(
            code=str(exc.status_code),
            message=exc.detail,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error.model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "")
        logger.error(
            "unhandled_exception",
            exc_type=type(exc).__name__,
            exc_msg=str(exc),
            method=request.method,
            path=request.url.path,
            request_id=request_id,
            exc_info=exc,
        )
        error = ErrorResponse(
            code="500",
            message="Internal server error",
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content=error.model_dump(),
        )


app = create_app()


@app.get("/")
async def root():
    return {"message": "AI Commerce Orchestrator API", "docs": "/docs"}
