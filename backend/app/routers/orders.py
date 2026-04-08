from fastapi import APIRouter, Query

from app.schemas.woocommerce import WCOrder
from app.services import orders as order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=WCOrder)
async def get_order(order_id: int):
    return await order_service.get_order(order_id)


@router.get("", response_model=list[WCOrder])
async def list_orders(
    customer: int = Query(...),
    status: str | None = Query(None),
):
    return await order_service.list_orders_by_customer(customer, status)
