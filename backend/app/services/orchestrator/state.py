from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class ConversationState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    confidence: float
    session_id: str
    trace_id: str
    channel: str
    user_id: str
    agent: str
    metadata: dict
