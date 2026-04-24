from app.services.orchestrator.state import ConversationState


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
