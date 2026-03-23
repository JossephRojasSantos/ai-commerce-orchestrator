from app.schemas.health import HealthResponse


class TestLiveness:
    def test_liveness_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "timestamp" in data

    def test_liveness_response_schema(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        HealthResponse(**resp.json())


class TestReadiness:
    def test_readiness_ok(self, client, mock_db_ok, mock_redis_ok):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db"] is True
        assert data["redis"] is True

    def test_readiness_db_down(self, client, mock_db_fail, mock_redis_ok):
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["db"] is False
        assert data["redis"] is True
        assert data["status"] == "degraded"

    def test_readiness_redis_down(self, client, mock_db_ok, mock_redis_fail):
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["db"] is True
        assert data["redis"] is False
        assert data["status"] == "degraded"

    def test_readiness_both_down(self, client, mock_db_fail, mock_redis_fail):
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["db"] is False
        assert data["redis"] is False


class TestErrorHandling:
    def test_404_returns_error_response(self, client):
        resp = client.get("/ruta-inexistente")
        assert resp.status_code == 404
        data = resp.json()
        assert "code" in data
        assert "message" in data
        assert "request_id" in data

    def test_request_id_header(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers
