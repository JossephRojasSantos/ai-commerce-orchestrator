from app.services.orchestrator.state import ConversationState

_MAX_HANDOFFS = 2


def route_intent(state: ConversationState) -> str:
    """LangGraph conditional edge: map intent → node name."""
    intent = state.get("intent", "other")
    mapping = {
        "buy": "chat_agent",
        "track": "tracking_agent",
        "recommend": "reco_agent",
        "other": "fallback_agent",
    }
    return mapping.get(intent, "fallback_agent")


def check_handoff(state: ConversationState) -> str:
    """Post-agent edge: escalate to fallback when agent signals it cannot resolve."""
    if state.get("needs_handoff") and state.get("handoff_count", 0) < _MAX_HANDOFFS:
        return "fallback_agent"
    return "__end__"
