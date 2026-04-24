"""Unit tests for app/clients/llm.py — verifies OpenRouter headers and fallback payload."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.clients.llm import chat_complete


def _mock_response(content: str = "OK") -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


@pytest.mark.asyncio
async def test_chat_complete_sends_openrouter_headers():
    captured = {}

    async def fake_post(url, headers=None, json=None, **kwargs):
        captured["headers"] = headers
        captured["json"] = json
        return _mock_response("hola")

    with patch("app.clients.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        result = await chat_complete([{"role": "user", "content": "test"}])

    assert result == "hola"
    assert "HTTP-Referer" in captured["headers"]
    assert "X-Title" in captured["headers"]
    assert captured["headers"]["X-OR-Prompt-Training"] == "false"
    assert "Authorization" in captured["headers"]


@pytest.mark.asyncio
async def test_chat_complete_with_fallback_sets_models_field():
    captured = {}

    async def fake_post(url, headers=None, json=None, **kwargs):
        captured["json"] = json
        return _mock_response("resp")

    with patch("app.clients.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await chat_complete(
            [{"role": "user", "content": "test"}],
            model="openai/gpt-4o-mini",
            fallback="anthropic/claude-haiku-4-5",
        )

    assert captured["json"]["models"] == ["openai/gpt-4o-mini", "anthropic/claude-haiku-4-5"]
    assert captured["json"]["model"] == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_chat_complete_without_fallback_no_models_field():
    captured = {}

    async def fake_post(url, headers=None, json=None, **kwargs):
        captured["json"] = json
        return _mock_response("resp")

    with patch("app.clients.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await chat_complete([{"role": "user", "content": "test"}], model="openai/gpt-4o-mini")

    assert "models" not in captured["json"]


@pytest.mark.asyncio
async def test_chat_complete_defaults_to_llm_model_chat():
    captured = {}

    async def fake_post(url, headers=None, json=None, **kwargs):
        captured["json"] = json
        return _mock_response("resp")

    with patch("app.clients.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        from app.config import settings
        await chat_complete([{"role": "user", "content": "test"}])

    assert captured["json"]["model"] == settings.LLM_MODEL_CHAT


@pytest.mark.asyncio
async def test_chat_complete_raises_on_http_error():
    with patch("app.clients.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=MagicMock()
        )
        mock_client.post = AsyncMock(return_value=resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await chat_complete([{"role": "user", "content": "test"}])
