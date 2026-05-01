"""Integration tests: full graph flows with MemorySaver (no real Redis/LLM)."""

import time
from unittest.mock import AsyncMock, patch

from app.services.orchestrator.graph import build_graph, get_graph, process_message
from app.services.orchestrator.state import ConversationState
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver


def _get_test_graph():
    """Build graph with MemorySaver checkpointer."""
    with patch("app.services.orchestrator.graph.get_checkpointer", return_value=MemorySaver()):
        return build_graph()


async def test_buy_flow_e2e():
    graph = _get_test_graph()
    with patch(
        "app.services.orchestrator.router.chat_complete",
        new_callable=AsyncMock,
        return_value='{"intent":"buy","confidence":0.95}',
    ):
        with patch(
            "app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None
        ):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                with patch(
                    "app.services.orchestrator.agents.chat.chat_complete",
                    new_callable=AsyncMock,
                    return_value="Aquí tienes opciones de zapatos.",
                ):
                    config = {"configurable": {"thread_id": "web:test1"}}
                    from app.services.orchestrator.state import ConversationState
                    from langchain_core.messages import HumanMessage

                    state = ConversationState(
                        messages=[HumanMessage(content="quiero comprar zapatos")],
                        intent="",
                        confidence=0.0,
                        session_id="web:test1",
                        trace_id="t1",
                        channel="web",
                        user_id="test1",
                        agent="",
                        metadata={},
                        needs_handoff=False,
                        handoff_count=0,
                    )
                    result = await graph.ainvoke(state, config=config)
    assert result["intent"] == "buy"
    assert result["agent"] == "chat"
    assert len(result["messages"]) >= 2


async def test_track_flow_e2e():
    graph = _get_test_graph()
    mock_wc = AsyncMock()
    mock_wc._get = AsyncMock(
        return_value={"status": "completed", "date_created": "2026-04-01T00:00:00"}
    )

    with patch(
        "app.services.orchestrator.router.chat_complete",
        new_callable=AsyncMock,
        return_value='{"intent":"track","confidence":0.97}',
    ):
        with patch(
            "app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None
        ):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                with patch(
                    "app.services.orchestrator.agents.tracking.get_wc_client",
                    new_callable=AsyncMock,
                    return_value=mock_wc,
                ):
                    config = {"configurable": {"thread_id": "web:test2"}}
                    from app.services.orchestrator.state import ConversationState
                    from langchain_core.messages import HumanMessage

                    state = ConversationState(
                        messages=[HumanMessage(content="pedido 12345 dónde está")],
                        intent="",
                        confidence=0.0,
                        session_id="web:test2",
                        trace_id="t2",
                        channel="web",
                        user_id="test2",
                        agent="",
                        metadata={},
                        needs_handoff=False,
                        handoff_count=0,
                    )
                    result = await graph.ainvoke(state, config=config)
    assert result["intent"] == "track"
    assert result["agent"] == "tracking"


async def test_fallback_flow_e2e():
    graph = _get_test_graph()
    with patch("app.services.orchestrator.router.chat_complete", side_effect=Exception("LLM down")):
        with patch(
            "app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None
        ):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                config = {"configurable": {"thread_id": "web:test3"}}
                from app.services.orchestrator.state import ConversationState
                from langchain_core.messages import HumanMessage

                state = ConversationState(
                    messages=[HumanMessage(content="hola")],
                    intent="",
                    confidence=0.0,
                    session_id="web:test3",
                    trace_id="t3",
                    channel="web",
                    user_id="test3",
                    agent="",
                    metadata={},
                    needs_handoff=False,
                    handoff_count=0,
                )
                result = await graph.ainvoke(state, config=config)
    assert result["agent"] == "fallback"


async def test_state_persisted_between_messages():
    """Two consecutive messages on same thread share state."""
    graph = _get_test_graph()
    config = {"configurable": {"thread_id": "web:test4"}}
    from app.services.orchestrator.state import ConversationState
    from langchain_core.messages import HumanMessage

    base_state = dict(
        intent="",
        confidence=0.0,
        session_id="web:test4",
        trace_id="t4",
        channel="web",
        user_id="test4",
        agent="",
        metadata={},
        needs_handoff=False,
        handoff_count=0,
    )

    with patch(
        "app.services.orchestrator.router.chat_complete",
        new_callable=AsyncMock,
        return_value='{"intent":"other","confidence":0.8}',
    ):
        with patch(
            "app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None
        ):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                state1 = ConversationState(messages=[HumanMessage(content="hola")], **base_state)
                result1 = await graph.ainvoke(state1, config=config)

                state2 = ConversationState(
                    messages=[HumanMessage(content="adiós")], **{**base_state, "trace_id": "t4b"}
                )
                result2 = await graph.ainvoke(state2, config=config)

    assert len(result2["messages"]) >= len(result1["messages"])


async def test_process_message_function():
    with patch("app.services.orchestrator.graph.get_graph") as mock_get_graph:
        mock_graph = AsyncMock()
        from langchain_core.messages import AIMessage

        mock_graph.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Hola!")],
                "intent": "other",
                "agent": "fallback",
            }
        )
        mock_get_graph.return_value = mock_graph

        result = await process_message(
            channel="web",
            user_id="userX",
            text="hola",
            trace_id="trace-x",
        )

    assert result["reply"] == "Hola!"
    assert result["session_id"] == "web:userX"
    assert result["trace_id"] == "trace-x"


def test_get_graph_returns_cached_instance():
    """Covers graph.py lines 72-74: get_graph() builds once, returns same object."""
    import app.services.orchestrator.graph as graph_mod

    with patch("app.services.orchestrator.graph.get_checkpointer", return_value=MemorySaver()):
        graph_mod._graph = None  # reset
        g1 = get_graph()
        g2 = get_graph()  # second call uses cached _graph
    assert g1 is g2
    graph_mod._graph = None  # cleanup


async def test_agent_exception_triggers_fallback():
    """Covers graph.py lines 39-42: exception inside agent node → fallback."""
    graph = _get_test_graph()

    with patch(
        "app.services.orchestrator.router.chat_complete",
        new_callable=AsyncMock,
        return_value='{"intent":"buy","confidence":0.9}',
    ):
        with patch(
            "app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None
        ):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                with patch(
                    "app.services.orchestrator.agents.chat.run",
                    side_effect=Exception("agent crashed"),
                ):
                    config = {"configurable": {"thread_id": "web:test_exc"}}
                    state = ConversationState(
                        messages=[HumanMessage(content="quiero comprar algo")],
                        intent="",
                        confidence=0.0,
                        session_id="web:test_exc",
                        trace_id="t_exc",
                        channel="web",
                        user_id="test_exc",
                        agent="",
                        metadata={},
                        needs_handoff=False,
                        handoff_count=0,
                    )
                    result = await graph.ainvoke(state, config=config)

    assert result["agent"] == "fallback"


async def test_agent_degraded_triggers_fallback():
    """Covers graph.py lines 29-30: is_agent_degraded True → fallback skips agent."""
    import app.core.errors as errors_mod

    graph = _get_test_graph()

    # Mark "chat" agent as degraded
    errors_mod._degraded_until["chat"] = time.monotonic() + 60.0
    try:
        with patch(
            "app.services.orchestrator.router.chat_complete",
            new_callable=AsyncMock,
            return_value='{"intent":"buy","confidence":0.9}',
        ):
            with patch(
                "app.services.orchestrator.router.cache_get",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                    config = {"configurable": {"thread_id": "web:test_deg"}}
                    state = ConversationState(
                        messages=[HumanMessage(content="quiero comprar algo")],
                        intent="",
                        confidence=0.0,
                        session_id="web:test_deg",
                        trace_id="t_deg",
                        channel="web",
                        user_id="test_deg",
                        agent="",
                        metadata={},
                        needs_handoff=False,
                        handoff_count=0,
                    )
                    result = await graph.ainvoke(state, config=config)
    finally:
        errors_mod._degraded_until.pop("chat", None)

    assert result["agent"] == "fallback"


async def test_tracking_wc_error_escalates_to_fallback():
    """WC error in tracking_agent sets needs_handoff=True → check_handoff → fallback_agent."""
    from app.clients.woocommerce import WCServerError

    graph = _get_test_graph()

    with patch(
        "app.services.orchestrator.router.chat_complete",
        new_callable=AsyncMock,
        return_value='{"intent":"track","confidence":0.98}',
    ):
        with patch(
            "app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None
        ):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                with patch(
                    "app.services.orchestrator.agents.tracking.get_wc_client",
                    new_callable=AsyncMock,
                    side_effect=WCServerError(503, "timeout"),
                ):
                    config = {"configurable": {"thread_id": "web:test_handoff"}}
                    state = ConversationState(
                        messages=[HumanMessage(content="pedido 99999 dónde está")],
                        intent="",
                        confidence=0.0,
                        session_id="web:test_handoff",
                        trace_id="t_hf",
                        channel="web",
                        user_id="test_handoff",
                        agent="",
                        metadata={},
                        needs_handoff=False,
                        handoff_count=0,
                    )
                    result = await graph.ainvoke(state, config=config)

    assert result["agent"] == "fallback"
    assert result.get("needs_handoff") is True
