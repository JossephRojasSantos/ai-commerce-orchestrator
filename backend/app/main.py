import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.middleware import RequestIDMiddleware, setup_logging
from app.routers.health import router as health_router
from app.schemas.errors import ErrorResponse

logger = structlog.get_logger()


def create_app() -> FastAPI:
    setup_logging(settings)

    app = FastAPI(
        title="AI Commerce Orchestrator",
        version=settings.APP_VERSION,
        description="Backend base para agentes IA de comercio electrónico",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health_router)

    register_exception_handlers(app)
    return app


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            "http_error",
            status_code=exc.status_code,
            detail=exc.detail,
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
            exc_info=exc,
            request_id=request_id,
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
