from __future__ import annotations

import asyncio
import time

import structlog

from app.clients.embeddings import embed_query
from app.clients.llm import chat_complete
from app.config import settings
from app.schemas.rag import ProductHit, RAGRequest, RAGResponse
from app.services.rag.prompts import SYSTEM_RECOMMEND, USER_RECOMMEND, build_products_block
from app.services.rag.vector_store import get_vector_store

logger = structlog.get_logger()


async def recommend(req: RAGRequest) -> RAGResponse:
    start = time.monotonic()

    try:
        vector, store = await asyncio.wait_for(
            _embed_and_store(req.query),
            timeout=settings.RAG_TIMEOUT_SEC,
        )
        raw_hits = await asyncio.wait_for(
            store.search(vector, top_k=req.top_k, min_score=req.min_score),
            timeout=settings.RAG_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.warning("rag_timeout", query=req.query[:60])
        return RAGResponse(
            query=req.query,
            hits=[],
            answer=None,
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    hits = [ProductHit(score=h["score"], **h["payload"]) for h in raw_hits]

    answer: str | None = None
    if req.generate and hits and settings.RAG_LLM_ENABLED:
        products_block = build_products_block([h.model_dump() for h in hits])
        messages = [
            {"role": "system", "content": SYSTEM_RECOMMEND},
            {
                "role": "user",
                "content": USER_RECOMMEND.format(
                    query=req.query, products_block=products_block
                ),
            },
        ]
        try:
            answer = await asyncio.wait_for(
                chat_complete(messages, model=settings.LLM_MODEL_CHAT),
                timeout=settings.LLM_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("rag_llm_failed", error=str(exc))

    latency_ms = int((time.monotonic() - start) * 1000)
    logger.info("rag_recommend", hits=len(hits), latency_ms=latency_ms, generated=answer is not None)
    return RAGResponse(query=req.query, hits=hits, answer=answer, latency_ms=latency_ms)


async def _embed_and_store(query: str):
    vector = await embed_query(query)
    store = await get_vector_store()
    return vector, store
