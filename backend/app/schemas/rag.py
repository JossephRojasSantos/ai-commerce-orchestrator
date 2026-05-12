from pydantic import BaseModel, Field


class ProductHit(BaseModel):
    wc_id: int
    name: str
    slug: str
    price: str
    regular_price: str
    sale_price: str
    stock_status: str
    categories: list[str]
    permalink: str
    image: str
    short_description: str
    score: float


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.35, ge=0.0, le=1.0)
    generate: bool = True


class RAGResponse(BaseModel):
    query: str
    hits: list[ProductHit]
    answer: str | None = None
    latency_ms: int
