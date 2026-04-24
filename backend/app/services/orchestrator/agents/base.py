from typing import Protocol

from app.services.orchestrator.state import ConversationState


class AgentProtocol(Protocol):
    async def run(self, state: ConversationState) -> dict: ...
