"""Unit tests for AgentRouter — regex fallback path (no LLM call)."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from app.services.orchestrator.router import Intent, _regex_fallback, classify_intent


@pytest.mark.parametrize(
    "text,expected",
    [
        ("quiero comprar zapatos", Intent.BUY),
        ("precio de la blusa", Intent.BUY),
        ("dónde está mi pedido 123", Intent.TRACK),
        ("tracking de mi envío", Intent.TRACK),
        ("qué me recomiendas", Intent.RECOMMEND),
        ("busco algo para regalo", Intent.RECOMMEND),
        ("hola", None),
        ("buenos días", None),
    ],
)
def test_regex_fallback(text, expected):
    result = _regex_fallback(text)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result.intent == expected
        assert result.confidence >= 0.5


@pytest.mark.parametrize(
    "text,expected_intent",
    [
        ("quiero comprar una camisa", Intent.BUY),
        ("pedido #555 dónde está", Intent.TRACK),
        ("recomiéndame algo similar", Intent.RECOMMEND),
    ],
)
async def test_classify_intent_regex_path(text, expected_intent):
    with patch("app.services.orchestrator.router.chat_complete", side_effect=Exception("LLM down")):
        with patch("app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                result = await classify_intent(text, "web:user1")
    assert result.intent == expected_intent


async def test_classify_intent_llm_path():
    llm_response = '{"intent": "buy", "confidence": 0.95}'
    with patch("app.services.orchestrator.router.chat_complete", new_callable=AsyncMock, return_value=llm_response):
        with patch("app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                result = await classify_intent("quiero comprar algo", "web:user2")
    assert result.intent == Intent.BUY
    assert result.confidence == 0.95


async def test_classify_intent_cache_hit():
    cached = {"intent": "track", "confidence": 0.88}
    with patch("app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=cached):
        result = await classify_intent("pedido 123", "web:user3")
    assert result.intent == Intent.TRACK
    assert result.confidence == 0.88


async def test_classify_intent_llm_invalid_json():
    with patch("app.services.orchestrator.router.chat_complete", new_callable=AsyncMock, return_value="not json"):
        with patch("app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                result = await classify_intent("hola", "web:user4")
    assert result.intent == Intent.OTHER


async def test_classify_intent_llm_code_block_response():
    """Covers router.py line 68: strip ```json ... ``` wrapper from LLM response."""
    llm_response = "```json\n{\"intent\": \"recommend\", \"confidence\": 0.88}\n```"
    with patch("app.services.orchestrator.router.chat_complete", new_callable=AsyncMock, return_value=llm_response):
        with patch("app.services.orchestrator.router.cache_get", new_callable=AsyncMock, return_value=None):
            with patch("app.services.orchestrator.router.cache_set", new_callable=AsyncMock):
                result = await classify_intent("qué me recomiendas", "web:user5")
    assert result.intent == Intent.RECOMMEND
    assert result.confidence == 0.88


def test_fixtures_coverage():
    fixtures_path = Path(__file__).parent / "fixtures" / "conversations.json"
    data = json.loads(fixtures_path.read_text())
    correct = 0
    for item in data:
        r = _regex_fallback(item["text"])
        predicted = r.intent.value if r else "other"
        if predicted == item["expected"]:
            correct += 1
    accuracy = correct / len(data)
    assert accuracy >= 0.50, f"Regex accuracy too low: {accuracy:.0%}"
