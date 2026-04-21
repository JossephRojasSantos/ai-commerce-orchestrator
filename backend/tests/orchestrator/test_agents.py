"""Unit tests for individual agents — all external deps mocked."""
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.services.orchestrator.agents import chat, fallback, recommendation, tracking
from app.services.orchestrator.agents.base import AgentProtocol  # noqa: F401 — ensures base.py coverage
from app.services.orchestrator.state import ConversationState


def _make_state(text: str, intent: str = "other", **kwargs) -> ConversationState:
    return ConversationState(
        messages=[HumanMessage(content=text)],
        intent=intent,
        confidence=0.9,
        session_id="web:user1",
        trace_id="trace-test",
        channel="web",
        user_id="user1",
        agent="",
        metadata={},
        **kwargs,
    )


# --- FallbackAgent ---

async def test_fallback_returns_reply():
    state = _make_state("hola")
    result = await fallback.run(state)
    assert "messages" in result
    assert result["agent"] == "fallback"
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)


# --- RecoAgent ---

async def test_reco_returns_placeholder():
    state = _make_state("recomiéndame algo", intent="recommend")
    result = await recommendation.run(state)
    assert result["agent"] == "recommendation"
    assert "placeholder" in result["messages"][0].content.lower() or "sugerencias" in result["messages"][0].content.lower()


# --- ChatAgent ---

async def test_chat_agent_calls_llm():
    state = _make_state("quiero comprar zapatos", intent="buy")
    with patch("app.services.orchestrator.agents.chat.chat_complete", new_callable=AsyncMock, return_value="Aquí están las opciones."):
        result = await chat.run(state)
    assert result["agent"] == "chat"
    assert "opciones" in result["messages"][0].content


# --- TrackingAgent ---

async def test_tracking_no_order_id():
    state = _make_state("dónde está mi pedido", intent="track")
    result = await tracking.run(state)
    assert result["agent"] == "tracking"
    assert "número" in result["messages"][0].content.lower()


async def test_tracking_with_order_id():
    state = _make_state("pedido 12345", intent="track")
    mock_order = {"status": "processing", "date_created": "2026-04-20T10:00:00"}
    mock_wc = AsyncMock()
    mock_wc._get = AsyncMock(return_value=mock_order)
    with patch("app.services.orchestrator.agents.tracking.get_wc_client", new_callable=AsyncMock, return_value=mock_wc):
        result = await tracking.run(state)
    assert "12345" in result["messages"][0].content
    assert "proceso" in result["messages"][0].content


async def test_tracking_wc_error():
    from app.clients.woocommerce import WCServerError

    state = _make_state("pedido 99999", intent="track")
    mock_wc = AsyncMock()
    mock_wc._get = AsyncMock(side_effect=WCServerError(503, "down"))
    with patch("app.services.orchestrator.agents.tracking.get_wc_client", new_callable=AsyncMock, return_value=mock_wc):
        result = await tracking.run(state)
    assert "99999" in result["messages"][0].content


async def test_chat_agent_multi_turn_history():
    """Covers chat.py lines 19-22: HumanMessage + AIMessage in history loop."""
    state = ConversationState(
        messages=[
            HumanMessage(content="busco zapatos rojos"),
            AIMessage(content="Tenemos varios modelos, ¿qué talla?"),
            HumanMessage(content="talla 42"),
        ],
        intent="buy",
        confidence=0.9,
        session_id="web:u1",
        trace_id="t1",
        channel="web",
        user_id="u1",
        agent="",
        metadata={},
    )
    with patch("app.services.orchestrator.agents.chat.chat_complete", new_callable=AsyncMock, return_value="Aquí tienes opciones en talla 42."):
        result = await chat.run(state)
    assert result["agent"] == "chat"
    assert "42" in result["messages"][0].content
