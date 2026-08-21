from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_internal_api_key
from app.schemas.woocommerce import WCOrder
from app.services import orders as order_service

# Estados WC válidos para filtrar (evita pasar valores arbitrarios a la API de WooCommerce)
_ALLOWED_ORDER_STATUSES = {
    "pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed",
}

# Endpoints con PII de clientes: exigen key interna (server-to-server), no la key pública web.
router = APIRouter(
    prefix="/orders", tags=["orders"], dependencies=[Depends(require_internal_api_key)]
)


@router.get("/{order_id}", response_model=WCOrder)
async def get_order(order_id: int):
    return await order_service.get_order(order_id)


@router.get("", response_model=list[WCOrder])
async def list_orders(
    customer: int = Query(...),
    status: str | None = Query(None),
):
    if status is not None and status not in _ALLOWED_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="status_not_allowed")
    return await order_service.list_orders_by_customer(customer, status)
