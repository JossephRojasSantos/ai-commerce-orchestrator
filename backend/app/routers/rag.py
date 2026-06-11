from fastapi import APIRouter, Depends

from app.core.auth import require_api_key
from app.schemas.rag import RAGRequest, RAGResponse
from app.services.rag.recommendation import recommend

router = APIRouter(prefix="/v1/rag", tags=["rag"], dependencies=[Depends(require_api_key)])


@router.post("/recommend", response_model=RAGResponse)
async def rag_recommend(req: RAGRequest) -> RAGResponse:
    return await recommend(req)
