from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.clients.embeddings import embed_query, embed_texts
from app.config import settings


def _embedding_response(texts: list[str]) -> dict:
    return {
        "data": [
            {"index": i, "embedding": [0.1] * 1536}
            for i in range(len(texts))
        ]
    }


@pytest.mark.asyncio
@respx.mock
async def test_embed_texts_returns_vectors():
    respx.post(f"{settings.LLM_API_BASE}/embeddings").mock(
        return_value=httpx.Response(200, json=_embedding_response(["hello"]))
    )
    import app.clients.embeddings as emb_module
    emb_module._cache.clear()

    result = await embed_texts(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 1536


@pytest.mark.asyncio
@respx.mock
async def test_embed_texts_uses_cache():
    import app.clients.embeddings as emb_module
    emb_module._cache.clear()

    route = respx.post(f"{settings.LLM_API_BASE}/embeddings").mock(
        return_value=httpx.Response(200, json=_embedding_response(["cached"]))
    )

    await embed_texts(["cached"])
    await embed_texts(["cached"])

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_embed_query_returns_single_vector():
    respx.post(f"{settings.LLM_API_BASE}/embeddings").mock(
        return_value=httpx.Response(200, json=_embedding_response(["query"]))
    )
    import app.clients.embeddings as emb_module
    emb_module._cache.clear()

    vec = await embed_query("query")
    assert isinstance(vec, list)
    assert len(vec) == 1536


@pytest.mark.asyncio
@respx.mock
async def test_embed_texts_batches_large_input():
    import app.clients.embeddings as emb_module
    emb_module._cache.clear()

    texts = [f"text_{i}" for i in range(150)]
    route = respx.post(f"{settings.LLM_API_BASE}/embeddings").mock(
        side_effect=lambda req: httpx.Response(
            200,
            json=_embedding_response(
                ["x"] * len(req.content)  # rough — just need valid response shape
            ),
        )
    )

    # Patch to return correct sized responses per batch
    async def fake_fetch(ts):
        return [[0.1] * 1536 for _ in ts]

    with patch("app.clients.embeddings._fetch_embeddings", side_effect=fake_fetch):
        result = await embed_texts(texts)

    assert len(result) == 150
