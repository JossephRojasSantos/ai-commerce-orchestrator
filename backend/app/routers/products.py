from fastapi import APIRouter, Query

from app.schemas.woocommerce import WCProduct
from app.services import products as product_service

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[WCProduct])
async def list_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    search: str = Query(""),
    category: str = Query(""),
):
    return await product_service.list_products(page, per_page, search, category)


@router.get("/{product_id}", response_model=WCProduct)
async def get_product(product_id: int):
    return await product_service.get_product(product_id)
