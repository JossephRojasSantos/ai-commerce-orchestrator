from fastapi import APIRouter

from app.schemas.rag import RAGRequest, RAGResponse
from app.services.rag.recommendation import recommend

router = APIRouter(prefix="/v1/rag", tags=["rag"])


@router.post("/recommend", response_model=RAGResponse)
async def rag_recommend(req: RAGRequest) -> RAGResponse:
    return await recommend(req)
