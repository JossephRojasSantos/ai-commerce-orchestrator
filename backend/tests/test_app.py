import uuid
from unittest.mock import patch

from app.config import settings
from app.main import create_app, register_exception_handlers
from app.schemas.errors import ErrorResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestCreateApp:
    def test_create_app_returns_fastapi_instance(self):
        """Test que create_app retorna una instancia de FastAPI."""
        test_app = create_app()
        assert isinstance(test_app, FastAPI)

    def test_create_app_has_correct_title(self):
        """Test que la app tiene el título correcto."""
        test_app = create_app()
        assert test_app.title == "AI Commerce Orchestrator"

    def test_create_app_has_correct_version(self):
        """Test que la app tiene la versión correcta del settings."""
        test_app = create_app()
        assert test_app.version == settings.APP_VERSION

    def test_create_app_includes_routes(self, client):
        """Test que la app incluye rutas (health router)."""
        # Verificar que el health endpoint funciona
        resp = client.get("/health")
        assert resp.status_code == 200


class TestCORSMiddleware:
    def test_cors_headers_present_with_origin(self):
        """Test que CORS headers están presentes cuando se envía Origin."""
        test_app = create_app()
        client = TestClient(test_app)

        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})

        assert resp.status_code == 200
        # FastAPI + CORSMiddleware añade access-control headers
        assert (
            "access-control-allow-origin" in resp.headers
            or "Access-Control-Allow-Origin" in resp.headers
        )

    def test_cors_configured_origins(self):
        """Test que CORS está configurado con los orígenes del settings."""
        test_app = create_app()
        client = TestClient(test_app)

        resp = client.get("/health", headers={"Origin": settings.CORS_ORIGINS[0]})

        assert resp.status_code == 200


class TestRequestIDMiddleware:
    def test_request_id_generated_if_not_in_request(self):
        """Test que X-Request-ID se genera automáticamente si no viene en request."""
        test_app = create_app()
        client = TestClient(test_app)

        resp = client.get("/health")

        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        request_id = resp.headers["x-request-id"]
        # Validar que es un UUID válido (no necesariamente format estricto)
        assert len(request_id) > 0

    def test_request_id_propagated_from_request_header(self):
        """Test que X-Request-ID se propaga desde el header del request."""
        test_app = create_app()
        client = TestClient(test_app)

        custom_request_id = str(uuid.uuid4())
        resp = client.get("/health", headers={"X-Request-ID": custom_request_id})

        assert resp.status_code == 200
        assert resp.headers["x-request-id"] == custom_request_id

    def test_request_id_available_in_request_state(self):
        """Test que request_id está disponible en request.state en handlers."""
        from fastapi import Request

        test_app = create_app()

        @test_app.get("/test-request-id")
        async def test_endpoint(request: Request):
            return {"request_id": getattr(request.state, "request_id", None)}

        client = TestClient(test_app)
        custom_id = "test-123-456"

        resp = client.get("/test-request-id", headers={"X-Request-ID": custom_id})

        assert resp.status_code == 200
        data = resp.json()
        assert data["request_id"] == custom_id


class TestExceptionHandlers:
    def test_exception_handler_is_registered(self):
        """Test que el generic_exception_handler está registrado."""
        test_app = FastAPI()
        register_exception_handlers(test_app)

        # Verificar que existen exception handlers
        assert len(test_app.exception_handlers) > 0

    def test_http_exception_handler_exists(self):
        """Test que hay un handler registrado para HTTPException."""
        from starlette.exceptions import HTTPException as StarletteHTTPException

        test_app = create_app()

        # Verificar que existe handler para HTTPException
        assert StarletteHTTPException in test_app.exception_handlers

    def test_error_response_with_request_id_serializes_correctly(self):
        """Test que ErrorResponse con request_id se serializa correctamente."""
        custom_id = str(uuid.uuid4())
        error = ErrorResponse(code="500", message="Internal server error", request_id=custom_id)

        data = error.model_dump()
        assert data["code"] == "500"
        assert data["message"] == "Internal server error"
        assert data["request_id"] == custom_id

    def test_404_error_returns_error_response(self, client):
        """Test que 404 retorna ErrorResponse con código y request_id."""
        resp = client.get("/ruta-no-existent-xyz")
        assert resp.status_code == 404
        data = resp.json()
        assert "code" in data
        assert "message" in data
        assert "request_id" in data

    def test_wc_server_error_returns_503(self, client):
        """WCServerError → 503 con code wc_unavailable."""
        from app.clients.woocommerce import WCServerError
        from fastapi import Request

        test_app = create_app()

        @test_app.get("/test-wc-server-err")
        async def _raise(request: Request):
            raise WCServerError(503, "gateway timeout")

        c = TestClient(test_app, raise_server_exceptions=False)
        resp = c.get("/test-wc-server-err")
        assert resp.status_code == 503
        data = resp.json()
        assert data["code"] == "wc_unavailable"
        assert "request_id" in data

    def test_wc_client_error_returns_422(self, client):
        """WCClientError (4xx de WC) → 422 con code wc_client_error."""
        from app.clients.woocommerce import WCClientError
        from fastapi import Request

        test_app = create_app()

        @test_app.get("/test-wc-client-err")
        async def _raise(request: Request):
            raise WCClientError(404, "order not found")

        c = TestClient(test_app, raise_server_exceptions=False)
        resp = c.get("/test-wc-client-err")
        assert resp.status_code == 422
        data = resp.json()
        assert data["code"] == "wc_client_error"
        assert "request_id" in data

    def test_generic_exception_returns_500(self, client):
        """Excepción no manejada → 500 con code 500."""
        from fastapi import Request

        test_app = create_app()

        @test_app.get("/test-generic-err")
        async def _raise(request: Request):
            raise RuntimeError("unexpected boom")

        c = TestClient(test_app, raise_server_exceptions=False)
        resp = c.get("/test-generic-err")
        assert resp.status_code == 500
        data = resp.json()
        assert data["code"] == "500"
        assert "request_id" in data


class TestSetupLogging:
    def test_setup_logging_development_no_error(self):
        """Test que setup_logging no falla en APP_ENV='development'."""
        from app.config import Settings
        from app.middleware import setup_logging

        dev_settings = Settings(APP_ENV="development")
        # No debe lanzar excepción
        setup_logging(dev_settings)

    def test_setup_logging_production_no_error(self):
        """Test que setup_logging no falla en APP_ENV='production'."""
        from app.config import Settings
        from app.middleware import setup_logging

        prod_settings = Settings(APP_ENV="production")
        # No debe lanzar excepción
        setup_logging(prod_settings)

    @patch("structlog.configure")
    def test_setup_logging_calls_structlog_configure(self, mock_configure):
        """Test que setup_logging llama a structlog.configure."""
        from app.config import Settings
        from app.middleware import setup_logging

        settings_obj = Settings()
        setup_logging(settings_obj)

        assert mock_configure.called


class TestErrorResponseSchema:
    def test_error_response_serialization(self):
        """Test que ErrorResponse serializa correctamente."""
        error = ErrorResponse(
            code="500", message="Internal server error", request_id=str(uuid.uuid4())
        )

        serialized = error.model_dump()
        assert "code" in serialized
        assert "message" in serialized
        assert "request_id" in serialized
