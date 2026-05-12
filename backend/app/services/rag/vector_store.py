from __future__ import annotations

import asyncio
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings

logger = structlog.get_logger()

_client: AsyncQdrantClient | None = None
_lock = asyncio.Lock()


class VectorStore:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def ensure_collection(self) -> None:
        existing = {c.name for c in (await self._client.get_collections()).collections}
        if settings.QDRANT_COLLECTION in existing:
            return
        await self._client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=qmodels.VectorParams(
                size=settings.QDRANT_VECTOR_SIZE,
                distance=qmodels.Distance.COSINE,
            ),
        )
        logger.info("qdrant_collection_created", collection=settings.QDRANT_COLLECTION)

    async def upsert(self, points: list[dict[str, Any]]) -> None:
        records = [
            qmodels.PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {}),
            )
            for p in points
        ]
        await self._client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=records,
            wait=True,
        )

    async def search(
        self,
        vector: list[float],
        top_k: int | None = None,
        min_score: float | None = None,
        filters: qmodels.Filter | None = None,
    ) -> list[dict[str, Any]]:
        k = top_k or settings.RAG_TOP_K
        results = await self._client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vector,
            limit=k,
            score_threshold=min_score or settings.RAG_MIN_SCORE,
            query_filter=filters,
            with_payload=True,
        )
        return [{"id": r.id, "score": r.score, "payload": r.payload} for r in results]

    async def delete(self, ids: list[int | str]) -> None:
        await self._client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=qmodels.PointIdsList(points=ids),
            wait=True,
        )

    async def health(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False


async def get_vector_store() -> VectorStore:
    global _client
    async with _lock:
        if _client is None:
            _client = AsyncQdrantClient(url=settings.QDRANT_URL)
            store = VectorStore(_client)
            await store.ensure_collection()
            logger.info("qdrant_connected", url=settings.QDRANT_URL)
            return store
    return VectorStore(_client)
