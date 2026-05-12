from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.rag import ProductHit, RAGResponse

_FAKE_RESPONSE = RAGResponse(
    query="muñeca",
    hits=[
        ProductHit(
            wc_id=1,
            name="Muñeca Mágica",
            slug="muneca-magica",
            price="25.00",
            regular_price="30.00",
            sale_price="25.00",
            stock_status="instock",
            categories=["Muñecas"],
            permalink="https://tiendamagica.shop/producto/muneca-magica",
            image="",
            short_description="Una muñeca encantada",
            score=0.85,
        )
    ],
    answer="Te recomiendo la Muñeca Mágica.",
    latency_ms=120,
)


@pytest.mark.asyncio
async def test_rag_recommend_ok():
    with patch(
        "app.routers.rag.recommend",
        new_callable=AsyncMock,
        return_value=_FAKE_RESPONSE,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/rag/recommend",
                json={"query": "muñeca", "top_k": 5, "min_score": 0.35, "generate": True},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "muñeca"
    assert len(data["hits"]) == 1
    assert data["hits"][0]["name"] == "Muñeca Mágica"
    assert data["answer"] == "Te recomiendo la Muñeca Mágica."


@pytest.mark.asyncio
async def test_rag_recommend_empty_query_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/rag/recommend",
            json={"query": "", "top_k": 5},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rag_recommend_no_hits():
    empty = RAGResponse(query="xyz", hits=[], answer=None, latency_ms=50)
    with patch("app.routers.rag.recommend", new_callable=AsyncMock, return_value=empty):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/rag/recommend", json={"query": "xyz"})

    assert resp.status_code == 200
    assert resp.json()["hits"] == []
