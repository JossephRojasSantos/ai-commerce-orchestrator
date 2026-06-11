"""Tests del fallback inteligente: saludos, cortesía y FAQs sin LLM."""

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
from langchain_core.messages import HumanMessage


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
        ("asdfgh xyz", _REPLY_DEFAULT),
        ("el clima está raro hoy", _REPLY_DEFAULT),
    ],
)
def test_resolve_reply(text, expected):
    assert _resolve_reply(text) == expected


def test_greeting_token_not_substring():
    # "hola" como token, no debe activarse dentro de otras palabras
    assert _resolve_reply("me gusta holanda") == _REPLY_DEFAULT


@pytest.mark.asyncio
async def test_run_returns_fallback_agent():
    state = {
        "messages": [HumanMessage(content="hola")],
        "intent": "other",
        "session_id": "test",
        "trace_id": "t1",
    }
    out = await run(state)
    assert out["agent"] == "fallback"
    assert out["messages"][0].content == _REPLY_GREETING
