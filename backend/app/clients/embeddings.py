from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

_cache: dict[str, list[float]] = {}
_cache_lock = asyncio.Lock()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    results: list[list[float] | None] = [None] * len(texts)
    uncached_idx: list[int] = []
    uncached_texts: list[str] = []

    async with _cache_lock:
        for i, t in enumerate(texts):
            if t in _cache:
                results[i] = _cache[t]
            else:
                uncached_idx.append(i)
                uncached_texts.append(t)

    if uncached_texts:
        vectors = await _fetch_embeddings(uncached_texts)
        async with _cache_lock:
            for idx, vec, text in zip(uncached_idx, vectors, uncached_texts, strict=False):
                _cache[text] = vec
                results[idx] = vec

    return results  # type: ignore[return-value]


async def embed_query(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]


async def _fetch_embeddings(texts: list[str]) -> list[list[float]]:
    batch_size = settings.EMBEDDINGS_BATCH_SIZE
    all_vectors: list[list[float]] = []

    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            payload: dict[str, Any] = {"model": settings.EMBEDDINGS_MODEL, "input": batch}
            resp = await client.post(
                f"{settings.LLM_API_BASE}/embeddings",
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda x: x["index"])
            all_vectors.extend(item["embedding"] for item in data)

    logger.info("embeddings_fetched", count=len(texts), model=settings.EMBEDDINGS_MODEL)
    return all_vectors
