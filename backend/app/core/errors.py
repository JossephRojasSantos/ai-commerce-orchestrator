import asyncio
import time
from collections import defaultdict

import structlog

logger = structlog.get_logger()

_failure_counts: dict[str, int] = defaultdict(int)
_degraded_until: dict[str, float] = {}
_RECOVERY_WINDOW = 60.0  # seconds before circuit resets


def record_agent_failure(agent_name: str, threshold: int) -> bool:
    """Record failure. Returns True if agent should be marked degraded."""
    now = time.monotonic()
    if _degraded_until.get(agent_name, 0) > now:
        return True
    _failure_counts[agent_name] += 1
    if _failure_counts[agent_name] >= threshold:
        _degraded_until[agent_name] = now + _RECOVERY_WINDOW
        _failure_counts[agent_name] = 0
        logger.warning("agent_circuit_open", agent=agent_name, recovery_in=_RECOVERY_WINDOW)
        return True
    return False


def is_agent_degraded(agent_name: str) -> bool:
    return _degraded_until.get(agent_name, 0) > time.monotonic()


def record_agent_success(agent_name: str) -> None:
    _failure_counts[agent_name] = 0
    _degraded_until.pop(agent_name, None)


async def run_with_timeout(coro: object, deadline: float, agent_name: str):
    try:
        return await asyncio.wait_for(coro, timeout=deadline)
    except TimeoutError:
        logger.error("agent_timeout", agent=agent_name, timeout=deadline)
        raise
