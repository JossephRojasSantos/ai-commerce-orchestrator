from unittest.mock import AsyncMock, patch

import pytest
from app.schemas.rag import RAGRequest, RAGResponse
from app.services.rag.recommendation import recommend

_FAKE_HIT = {
    "id": 1,
    "score": 0.85,
    "payload": {
        "wc_id": 1,
        "name": "Muñeca Mágica",
        "slug": "muneca-magica",
        "price": "25.00",
        "regular_price": "30.00",
        "sale_price": "25.00",
        "stock_status": "instock",
        "categories": ["Muñecas"],
        "permalink": "https://tiendamagica.shop/producto/muneca-magica",
        "image": "",
        "short_description": "Una muñeca encantada",
    },
}


@pytest.mark.asyncio
async def test_recommend_returns_hits_with_answer():
    req = RAGRequest(query="muñeca para niña", generate=True)

    with (
        patch("app.services.rag.recommendation.embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536),
        patch("app.services.rag.recommendation.get_vector_store", new_callable=AsyncMock) as mock_store_fn,
        patch("app.services.rag.recommendation.chat_complete", new_callable=AsyncMock, return_value="Te recomiendo la Muñeca Mágica."),
    ):
        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=[_FAKE_HIT])
        mock_store_fn.return_value = mock_store

        result = await recommend(req)

    assert isinstance(result, RAGResponse)
    assert len(result.hits) == 1
    assert result.hits[0].name == "Muñeca Mágica"
    assert result.answer == "Te recomiendo la Muñeca Mágica."
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_recommend_no_hits_returns_empty():
    req = RAGRequest(query="producto inexistente", generate=True)

    with (
        patch("app.services.rag.recommendation.embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536),
        patch("app.services.rag.recommendation.get_vector_store", new_callable=AsyncMock) as mock_store_fn,
    ):
        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=[])
        mock_store_fn.return_value = mock_store

        result = await recommend(req)

    assert result.hits == []
    assert result.answer is None


@pytest.mark.asyncio
async def test_recommend_generate_false_skips_llm():
    req = RAGRequest(query="juguete", generate=False)

    with (
        patch("app.services.rag.recommendation.embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536),
        patch("app.services.rag.recommendation.get_vector_store", new_callable=AsyncMock) as mock_store_fn,
        patch("app.services.rag.recommendation.chat_complete", new_callable=AsyncMock) as mock_llm,
    ):
        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=[_FAKE_HIT])
        mock_store_fn.return_value = mock_store

        result = await recommend(req)

    mock_llm.assert_not_awaited()
    assert result.hits[0].name == "Muñeca Mágica"


@pytest.mark.asyncio
async def test_recommend_timeout_returns_empty():
    import asyncio
    req = RAGRequest(query="juguete", generate=False)

    with patch("app.services.rag.recommendation.embed_query", new_callable=AsyncMock, side_effect=asyncio.TimeoutError):
        result = await recommend(req)

    assert result.hits == []
    assert result.answer is None
