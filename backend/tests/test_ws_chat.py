"""Tests for the /ws/chat WebSocket endpoint."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from fastapi.testclient import TestClient

_API_KEY = "key-ws-test"


def _patch_auth(keys=None, env="development"):
    return patch(
        "app.routers.ws.settings",
        MagicMock(ALLOWED_API_KEYS=keys if keys is not None else [_API_KEY], APP_ENV=env),
    )


def _result(reply="Hola, ¿en qué te ayudo?", intent="chat"):
    return {"reply": reply, "intent": intent}


def test_ws_rejects_invalid_api_key():
    with _patch_auth():
        client = TestClient(app)
        try:
            with client.websocket_connect("/ws/chat?api_key=wrong") as ws:
                ws.receive_text()
            raised = False
        except Exception:
            raised = True
    assert raised


def test_ws_fail_closed_in_production_without_keys():
    with _patch_auth(keys=[], env="production"):
        client = TestClient(app)
        try:
            with client.websocket_connect("/ws/chat") as ws:
                ws.receive_text()
            raised = False
        except Exception:
            raised = True
    assert raised


def test_ws_open_in_dev_without_keys():
    with _patch_auth(keys=[], env="development"):
        client = TestClient(app)
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"type": "session_start"}))
            msg = json.loads(ws.receive_text())
    assert msg["type"] == "text"
    assert "Tienda Mágica" in msg["content"]


def test_ws_session_start_returns_welcome():
    with _patch_auth():
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chat?api_key={_API_KEY}") as ws:
            ws.send_text(json.dumps({"type": "session_start"}))
            msg = json.loads(ws.receive_text())
    assert msg["type"] == "text"
    assert "asistente" in msg["content"]


def test_ws_message_flow_replies():
    with (
        _patch_auth(),
        patch(
            "app.routers.ws.process_message",
            new_callable=AsyncMock,
            return_value=_result("Tenemos muñecas mágicas."),
        ),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chat?api_key={_API_KEY}") as ws:
            ws.send_text(json.dumps({"type": "message", "content": "qué muñecas tienen?"}))
            frames = [json.loads(ws.receive_text()) for _ in range(3)]

    types = [f["type"] for f in frames]
    assert types == ["typing", "typing_stop", "text"]
    assert frames[2]["content"] == "Tenemos muñecas mágicas."


def test_ws_invalid_json_and_empty_text_ignored():
    with (
        _patch_auth(),
        patch(
            "app.routers.ws.process_message",
            new_callable=AsyncMock,
            return_value=_result("ok"),
        ),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chat?api_key={_API_KEY}") as ws:
            ws.send_text("not-json{{{")
            ws.send_text(json.dumps({"type": "other"}))
            ws.send_text(json.dumps({"type": "message", "content": "   "}))
            # Solo este produce respuesta
            ws.send_text(json.dumps({"type": "message", "content": "hola"}))
            frames = [json.loads(ws.receive_text()) for _ in range(3)]
    assert [f["type"] for f in frames] == ["typing", "typing_stop", "text"]


def test_ws_process_error_returns_fallback():
    with (
        _patch_auth(),
        patch(
            "app.routers.ws.process_message",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chat?api_key={_API_KEY}") as ws:
            ws.send_text(json.dumps({"type": "message", "content": "hola"}))
            frames = [json.loads(ws.receive_text()) for _ in range(3)]
    assert frames[2]["type"] == "text"
    assert "error" in frames[2]["content"].lower()
