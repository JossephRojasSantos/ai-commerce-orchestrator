"""Unit tests for intent → node routing."""

import pytest
from app.services.orchestrator.handoff import route_intent
from app.services.orchestrator.state import ConversationState


def _state(intent: str) -> ConversationState:
    return ConversationState(
        messages=[],
        intent=intent,
        confidence=0.9,
        session_id="web:u1",
        trace_id="t1",
        channel="web",
        user_id="u1",
        agent="",
        metadata={},
    )


@pytest.mark.parametrize(
    "intent,expected_node",
    [
        ("buy", "chat_agent"),
        ("track", "tracking_agent"),
        ("recommend", "reco_agent"),
        ("other", "fallback_agent"),
        ("unknown_value", "fallback_agent"),
    ],
)
def test_route_intent(intent, expected_node):
    assert route_intent(_state(intent)) == expected_node
