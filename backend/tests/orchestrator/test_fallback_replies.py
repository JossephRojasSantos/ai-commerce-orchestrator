"""Tests del fallback inteligente: saludos, cortesía y FAQs sin LLM."""

from unittest.mock import AsyncMock, patch

import pytest
from app.services.orchestrator.agents.fallback import (
    _REPLY_BYE,
    _REPLY_DEFAULT,
    _REPLY_GREETING,
    _REPLY_PAYMENT,
    _REPLY_RETURNS,
    _REPLY_SHIPPING,
    _REPLY_THANKS,
    _resolve_reply,
    run,
)
from langchain_core.messages import AIMessage, HumanMessage


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hola", _REPLY_GREETING),
        ("¡Hola!", _REPLY_GREETING),
        ("Buenos días", _REPLY_GREETING),
        ("buenas tardes", _REPLY_GREETING),
        ("gracias!", _REPLY_THANKS),
        ("Perfecto, gracias", _REPLY_THANKS),
        ("adiós", _REPLY_BYE),
        ("hasta luego", _REPLY_BYE),
        ("cuánto cuesta el envío?", _REPLY_SHIPPING),
        ("en cuánto llega a Cali?", _REPLY_SHIPPING),
        ("qué métodos de pago aceptan?", _REPLY_PAYMENT),
        ("puedo pagar con Nequi?", _REPLY_PAYMENT),
        ("cómo hago una devolución?", _REPLY_RETURNS),
        ("tienen garantía?", _REPLY_RETURNS),
        # catch-all (sin keyword) → None: run() lo escala al LLM
        ("asdfgh xyz", None),
        ("el clima está raro hoy", None),
        ("Hola! Test", _REPLY_GREETING),  # bug B: puntuación interna por token
    ],
)
def test_resolve_reply(text, expected):
    assert _resolve_reply(text) == expected


def test_greeting_token_not_substring():
    # "hola" como token, no debe activarse dentro de otras palabras
    assert _resolve_reply("me gusta holanda") is None


@pytest.mark.asyncio
async def test_run_fast_reply_for_greeting():
    state = {
        "messages": [HumanMessage(content="hola")],
        "intent": "other",
        "session_id": "test",
        "trace_id": "t1",
    }
    out = await run(state)
    assert out["agent"] == "fallback"
    assert out["messages"][0].content == _REPLY_GREETING


@pytest.mark.asyncio
async def test_run_catch_all_escalates_to_chat():
    state = {
        "messages": [HumanMessage(content="cuéntame algo de la tienda")],
        "intent": "other",
        "session_id": "test",
        "trace_id": "t1",
    }
    chat_out = {"messages": [AIMessage(content="respuesta LLM")], "agent": "chat"}
    with patch(
        "app.services.orchestrator.agents.chat.run",
        new_callable=AsyncMock,
        return_value=chat_out,
    ) as mock_chat:
        out = await run(state)

    mock_chat.assert_called_once()
    assert out["agent"] == "chat"
    assert out["messages"][0].content == "respuesta LLM"


@pytest.mark.asyncio
async def test_run_catch_all_falls_back_when_chat_fails():
    state = {
        "messages": [HumanMessage(content="cuéntame algo")],
        "intent": "other",
        "session_id": "test",
        "trace_id": "t1",
    }
    with patch(
        "app.services.orchestrator.agents.chat.run",
        new_callable=AsyncMock,
        side_effect=Exception("LLM down"),
    ):
        out = await run(state)

    assert out["agent"] == "fallback"
    assert out["messages"][0].content == _REPLY_DEFAULT
