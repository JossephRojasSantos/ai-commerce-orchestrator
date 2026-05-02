from unittest.mock import patch

import pytest
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


# ---------------------------------------------------------------------------
# AI-121 — Structured logging with trace_id in orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_message_logs_start_with_trace_id():
    """process_message binds trace_id to structlog context before invoking graph."""
    from unittest.mock import AsyncMock, patch

    logged_calls = []

    class CapturingLogger:
        def info(self, event, **kw):
            logged_calls.append((event, kw))

        def warning(self, event, **kw):
            pass

        def error(self, event, **kw):
            pass

    with patch("app.services.orchestrator.graph.logger", CapturingLogger()):
        with patch("app.services.orchestrator.graph.get_graph") as mock_get_graph:
            mock_graph = AsyncMock()
            from langchain_core.messages import AIMessage

            mock_graph.ainvoke = AsyncMock(
                return_value={
                    "messages": [AIMessage(content="ok")],
                    "intent": "other",
                    "agent": "fallback",
                }
            )
            mock_get_graph.return_value = mock_graph

            from app.services.orchestrator.graph import process_message

            await process_message(
                channel="web",
                user_id="u1",
                text="hola",
                trace_id="trace-abc-123",
            )

    events = [e for e, _ in logged_calls]
    assert "orchestrator.start" in events
    assert "orchestrator.done" in events


@pytest.mark.asyncio
async def test_process_message_done_log_has_intent_and_agent():
    """orchestrator.done log contains intent and agent fields."""
    from unittest.mock import AsyncMock, patch

    done_kwargs = {}

    class CapturingLogger:
        def info(self, event, **kw):
            if event == "orchestrator.done":
                done_kwargs.update(kw)

        def warning(self, *a, **kw):
            pass

        def error(self, *a, **kw):
            pass

    with patch("app.services.orchestrator.graph.logger", CapturingLogger()):
        with patch("app.services.orchestrator.graph.get_graph") as mock_get_graph:
            mock_graph = AsyncMock()
            from langchain_core.messages import AIMessage

            mock_graph.ainvoke = AsyncMock(
                return_value={
                    "messages": [AIMessage(content="ok")],
                    "intent": "buy",
                    "agent": "chat",
                }
            )
            mock_get_graph.return_value = mock_graph

            from app.services.orchestrator.graph import process_message

            await process_message(
                channel="web", user_id="u2", text="quiero zapatos", trace_id="t-xyz"
            )

    assert done_kwargs.get("intent") == "buy"
    assert done_kwargs.get("agent") == "chat"
    assert "duration_ms" in done_kwargs
