from unittest.mock import patch

from app.main import app
from fastapi.testclient import TestClient


def test_request_log_has_required_fields():
    with patch("app.middleware.log") as mock_log:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/", headers={"X-Request-ID": "test-req-abc"})

    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "test-req-abc"

    mock_log.info.assert_called_once()
    _, kwargs = mock_log.info.call_args
    assert kwargs["method"] == "GET"
    assert kwargs["path"] == "/health/"
    assert kwargs["status"] == 200
    assert isinstance(kwargs["duration_ms"], float)
    assert kwargs["duration_ms"] >= 0


def test_request_log_has_trace_id():
    with patch("app.middleware.log") as mock_log:
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/health/")

    mock_log.info.assert_called_once()
    _, kwargs = mock_log.info.call_args
    assert "trace_id" in kwargs
    assert len(kwargs["trace_id"]) > 0


def test_request_id_header_generated_when_absent():
    client = TestClient(app)
    resp = client.get("/health/")

    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0


def test_request_id_header_propagated():
    client = TestClient(app)
    resp = client.get("/health/", headers={"X-Request-ID": "my-custom-id"})

    assert resp.headers["X-Request-ID"] == "my-custom-id"


def test_metrics_endpoint_returns_prometheus_format():
    client = TestClient(app)
    resp = client.get("/metrics")

    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
    assert "# HELP" in resp.text
    assert "# TYPE" in resp.text


def test_metrics_counter_increments_on_request():
    client = TestClient(app)
    client.get("/health/")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total{" in resp.text
