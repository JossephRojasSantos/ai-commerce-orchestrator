
import structlog
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.config import settings
from app.core.errors import (
    is_agent_degraded,
    record_agent_failure,
    record_agent_success,
    run_with_timeout,
)
from app.services.orchestrator.agents import chat, fallback, recommendation, tracking
from app.services.orchestrator.checkpointer import get_checkpointer
from app.services.orchestrator.handoff import route_intent
from app.services.orchestrator.router import classify_intent
from app.services.orchestrator.state import ConversationState

logger = structlog.get_logger()


async def _router_node(state: ConversationState) -> dict:
    last = state["messages"][-1]
    text = last.content if hasattr(last, "content") else str(last)
    result = await classify_intent(text, state["session_id"])
    return {"intent": result.intent.value, "confidence": result.confidence}


def _make_agent_node(agent_module, name: str):
    async def node(state: ConversationState) -> dict:
        if is_agent_degraded(name):
            logger.warning("agent_degraded_skip", agent=name)
            return await fallback.run(state)
        try:
            output = await run_with_timeout(
                agent_module.run(state),
                timeout=settings.ORCHESTRATOR_AGENT_TIMEOUT,
                agent_name=name,
            )
            record_agent_success(name)
            return output
        except (TimeoutError, Exception) as exc:
            degraded = record_agent_failure(name, settings.ORCHESTRATOR_CIRCUIT_BREAKER_THRESHOLD)
            logger.error("agent_error", agent=name, error=str(exc), degraded=degraded)
            return await fallback.run(state)

    node.__name__ = f"{name}_node"
    return node


def build_graph():
    builder = StateGraph(ConversationState)

    builder.add_node("router", _router_node)
    builder.add_node("chat_agent", _make_agent_node(chat, "chat"))
    builder.add_node("tracking_agent", _make_agent_node(tracking, "tracking"))
    builder.add_node("reco_agent", _make_agent_node(recommendation, "recommendation"))
    builder.add_node("fallback_agent", _make_agent_node(fallback, "fallback"))

    builder.set_entry_point("router")
    builder.add_conditional_edges("router", route_intent)

    for node in ("chat_agent", "tracking_agent", "reco_agent", "fallback_agent"):
        builder.add_edge(node, END)

    checkpointer = get_checkpointer()
    return builder.compile(checkpointer=checkpointer)


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def process_message(
    channel: str,
    user_id: str,
    text: str,
    trace_id: str,
    metadata: dict | None = None,
) -> dict:
    graph = get_graph()
    session_id = f"{channel}:{user_id}"
    config = {"configurable": {"thread_id": session_id}}

    initial_state: ConversationState = {
        "messages": [HumanMessage(content=text)],
        "intent": "",
        "confidence": 0.0,
        "session_id": session_id,
        "trace_id": trace_id,
        "channel": channel,
        "user_id": user_id,
        "agent": "",
        "metadata": metadata or {},
    }

    final_state = await graph.ainvoke(initial_state, config=config)
    last_msg = final_state["messages"][-1]
    return {
        "reply": last_msg.content if hasattr(last_msg, "content") else str(last_msg),
        "intent": final_state.get("intent", "other"),
        "agent": final_state.get("agent", ""),
        "session_id": session_id,
        "trace_id": trace_id,
    }
