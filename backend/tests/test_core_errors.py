"""Coverage for app/core/errors.py — circuit breaker logic."""

import asyncio
import time

import pytest
from app.core import errors as err_module
from app.core.errors import (
    is_agent_degraded,
    record_agent_failure,
    record_agent_success,
    run_with_timeout,
)


@pytest.fixture(autouse=True)
def reset_circuit():
    err_module._failure_counts.clear()
    err_module._degraded_until.clear()
    yield
    err_module._failure_counts.clear()
    err_module._degraded_until.clear()


def test_record_failure_below_threshold():
    degraded = record_agent_failure("test_agent", threshold=3)
    assert not degraded
    assert not is_agent_degraded("test_agent")


def test_record_failure_reaches_threshold():
    record_agent_failure("test_agent", threshold=2)
    degraded = record_agent_failure("test_agent", threshold=2)
    assert degraded
    assert is_agent_degraded("test_agent")


def test_already_degraded_returns_true_immediately():
    err_module._degraded_until["test_agent"] = time.monotonic() + 60
    result = record_agent_failure("test_agent", threshold=1)
    assert result is True


def test_record_success_resets_circuit():
    record_agent_failure("test_agent", threshold=1)
    record_agent_failure("test_agent", threshold=1)
    assert is_agent_degraded("test_agent")
    record_agent_success("test_agent")
    assert not is_agent_degraded("test_agent")


def test_is_agent_degraded_unknown_agent():
    assert not is_agent_degraded("nonexistent")


@pytest.mark.asyncio
async def test_run_with_timeout_success():
    async def fast():
        return 42

    result = await run_with_timeout(fast(), deadline=5.0, agent_name="test")
    assert result == 42


@pytest.mark.asyncio
async def test_run_with_timeout_raises_on_timeout():
    async def slow():
        await asyncio.sleep(10)

    with pytest.raises(TimeoutError):
        await run_with_timeout(slow(), deadline=0.01, agent_name="slow_agent")
