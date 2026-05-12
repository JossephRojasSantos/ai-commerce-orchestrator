from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.rag.vector_store import VectorStore, get_vector_store


def _make_client(collections=None):
    client = AsyncMock()
    col_list = MagicMock()
    col_list.collections = collections or []
    client.get_collections = AsyncMock(return_value=col_list)
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_ensure_collection_creates_when_missing():
    client = _make_client(collections=[])
    store = VectorStore(client)
    await store.ensure_collection()
    client.create_collection.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_collection_skips_when_exists():
    existing = MagicMock()
    existing.name = "wc_products"
    client = _make_client(collections=[existing])
    store = VectorStore(client)
    await store.ensure_collection()
    client.create_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_calls_client():
    client = _make_client()
    store = VectorStore(client)
    points = [{"id": 1, "vector": [0.1] * 1536, "payload": {"name": "Toy"}}]
    await store.upsert(points)
    client.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_returns_formatted_hits():
    hit = MagicMock()
    hit.id = 42
    hit.score = 0.9
    hit.payload = {"name": "Toy", "price": "10.00"}

    client = _make_client()
    client.search = AsyncMock(return_value=[hit])
    store = VectorStore(client)

    results = await store.search([0.1] * 1536)

    assert len(results) == 1
    assert results[0]["id"] == 42
    assert results[0]["score"] == 0.9
    assert results[0]["payload"]["name"] == "Toy"


@pytest.mark.asyncio
async def test_delete_calls_client():
    client = _make_client()
    store = VectorStore(client)
    await store.delete([1, 2, 3])
    client.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_returns_true_on_success():
    client = _make_client()
    store = VectorStore(client)
    assert await store.health() is True


@pytest.mark.asyncio
async def test_health_returns_false_on_error():
    client = _make_client()
    client.get_collections = AsyncMock(side_effect=Exception("connection refused"))
    store = VectorStore(client)
    assert await store.health() is False


@pytest.mark.asyncio
async def test_get_vector_store_singleton():
    import app.services.rag.vector_store as vs_module

    original_client = vs_module._client
    vs_module._client = None

    mock_client = _make_client()
    with patch("app.services.rag.vector_store.AsyncQdrantClient", return_value=mock_client):
        store1 = await get_vector_store()
        store2 = await get_vector_store()

    assert isinstance(store1, VectorStore)
    assert isinstance(store2, VectorStore)

    vs_module._client = original_client
