"""Notificaciones salientes — confirmación WhatsApp de pedidos contraentrega (feature 011)."""

import re

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.core.auth import require_api_key
from app.integrations.whatsapp.client import send_template_message, send_text_message

logger = structlog.get_logger()

router = APIRouter(
    prefix="/v1/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_api_key)],
)

_COD_TEMPLATE = "tm_confirmacion"
_FALLBACK_TEXT = (
    "¡Hola{name}! 🪄 Recibimos tu pedido #{order} por {total} en Tienda Mágica. "
    "Pagarás al recibirlo. Te escribiremos por aquí para confirmar el envío. "
    "Responde este mensaje si tienes alguna duda."
)


class CodOrderNotification(BaseModel):
    phone: str = Field(description="Celular colombiano, 10 dígitos")
    order_number: str = Field(min_length=1, max_length=20)
    total: str = Field(min_length=1, max_length=30)
    customer_name: str = Field(default="", max_length=100)

    @field_validator("phone")
    @classmethod
    def _phone_co(cls, v: str) -> str:
        digits = re.sub(r"\D+", "", v)
        if digits.startswith("57") and len(digits) == 12:
            digits = digits[2:]
        if len(digits) != 10 or not digits.startswith("3"):
            raise ValueError("celular colombiano inválido")
        return "57" + digits  # formato E.164 sin '+' que espera la Cloud API


@router.post("/cod-order")
async def notify_cod_order(req: CodOrderNotification) -> dict:
    """Envía la confirmación del pedido COD por WhatsApp.

    Intenta la plantilla aprobada tm_confirmacion (business-initiated);
    si Meta la rechaza (no aprobada aún), cae a mensaje de texto —
    que solo entrega dentro de una ventana de conversación abierta.
    """
    result = await send_template_message(
        req.phone,
        _COD_TEMPLATE,
        {"order_id": req.order_number, "total": req.total},
    )

    fallback_used = False
    if result.status == "failed":
        logger.warning(
            "cod_notify.template_failed",
            order=req.order_number,
            error=result.error,
        )
        first_name = f" {req.customer_name.split(' ')[0]}" if req.customer_name else ""
        text = _FALLBACK_TEXT.format(name=first_name, order=req.order_number, total=req.total)
        result = await send_text_message(req.phone, text)
        fallback_used = True

    logger.info(
        "cod_notify.result",
        order=req.order_number,
        status=result.status,
        fallback=fallback_used,
    )
    return {
        "status": result.status,
        "message_id": result.message_id,
        "fallback_used": fallback_used,
        "error": result.error,
    }
