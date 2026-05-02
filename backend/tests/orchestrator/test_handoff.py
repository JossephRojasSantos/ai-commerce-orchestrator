"""Unit tests for intent → node routing and handoff checks."""

import pytest
from app.services.orchestrator.handoff import check_handoff, route_intent
from app.services.orchestrator.state import ConversationState


def _state(intent: str, needs_handoff: bool = False, handoff_count: int = 0) -> ConversationState:
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
        needs_handoff=needs_handoff,
        handoff_count=handoff_count,
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


@pytest.mark.parametrize(
    "needs_handoff,handoff_count,expected",
    [
        (True, 0, "fallback_agent"),
        (True, 1, "fallback_agent"),
        (True, 2, "__end__"),  # at max → no more escalation
        (False, 0, "__end__"),
        (False, 1, "__end__"),
    ],
)
def test_check_handoff(needs_handoff, handoff_count, expected):
    state = _state("buy", needs_handoff=needs_handoff, handoff_count=handoff_count)
    assert check_handoff(state) == expected
