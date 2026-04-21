# Orchestrator Architecture — AI-26

## Agents

| Agent | Intent | Responsibility |
|-------|--------|---------------|
| `ChatAgent` | `buy` | Multi-step purchase flow via LLM |
| `TrackingAgent` | `track` | Extracts order ID, queries WC API |
| `RecoAgent` | `recommend` | Placeholder for RAG (AI-29) |
| `FallbackAgent` | `other` | Generic reply + WARN log |

## Endpoint

```
POST /v1/orchestrator/message
Content-Type: application/json

{
  "channel": "web|whatsapp",
  "user_id": "string",
  "text": "string",
  "metadata": {}
}
```

Response: `{ reply, intent, agent, session_id, trace_id }`

## ConversationState

```python
class ConversationState(TypedDict):
    messages: Annotated[list, add_messages]  # LangGraph message accumulator
    intent: str          # buy | track | recommend | other
    confidence: float
    session_id: str      # channel:user_id
    trace_id: str        # UUID propagated from HTTP request
    channel: str
    user_id: str
    agent: str           # last agent that replied
    metadata: dict
```

## Observability

- Every request gets a `trace_id` (UUID v4) injected into structlog contextvars by `RequestIDMiddleware`.
- All log lines automatically include `trace_id` via `merge_contextvars` processor.
- Agents log `trace_id` explicitly in their structured logs.

## Circuit Breaker

- Per-agent failure counter in memory (`core/errors.py`).
- Threshold configurable via `ORCHESTRATOR_CIRCUIT_BREAKER_THRESHOLD` (default 3).
- Degraded agent → `FallbackAgent` handles instead.
- Recovers after 60 s.

## Session ID Convention

`{channel}:{user_id}` — e.g. `web:550e8400`, `whatsapp:+573001234567`
