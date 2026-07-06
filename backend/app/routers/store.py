"""API de la tienda headless Next.js (fase 2 migración WP).

Auth: header `X-Store-Secret` compartido con el frontend en Hostinger. La
defensa principal es de red (firewall Oracle: solo IP Hostinger); el secreto
evita que un vecino de red o una mala config exponga el catálogo/órdenes.
"""

import hmac

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_db
from app.services import store

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/store", tags=["store"])


async def require_store_secret(x_store_secret: str = Header(default="")) -> None:
    if not settings.STORE_API_SECRET or not hmac.compare_digest(
        x_store_secret, settings.STORE_API_SECRET
    ):
        raise HTTPException(status_code=401, detail="unauthorized")


@router.get("/products", dependencies=[Depends(require_store_secret)])
async def list_products(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await store.list_products(db)


@router.get("/products/{slug}", dependencies=[Depends(require_store_secret)])
async def get_product(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    dto = await store.get_product(db, slug)
    if dto is None:
        raise HTTPException(status_code=404, detail="not_found")
    return dto


class OrderCopy(BaseModel):
    shopOrderId: str = Field(min_length=1, max_length=64)
    total: float = Field(gt=0)
    cliente: dict = Field(default_factory=dict)
    productos: list = Field(default_factory=list)
    dropi: dict = Field(default_factory=dict)


@router.post("/orders", status_code=201, dependencies=[Depends(require_store_secret)])
async def create_order_copy(body: OrderCopy, db: AsyncSession = Depends(get_db)) -> dict:
    order_id = await store.save_order(db, body.model_dump())
    return {"id": order_id, "shopOrderId": body.shopOrderId}
