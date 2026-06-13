"""Sincroniza el estado de fulfillment de Dropi → WooCommerce (feature 016).

El panel lee WooCommerce; Dropi avanza el estado del envío (guía, transportadora,
entregado, devolución) sin que la tienda se entere. Este servicio cruza cada orden
Dropi con su orden WC vía `shop_order_id` y:

  1. escribe siempre los metadatos `_dropi_*` (estado real, transportadora, guía);
  2. (opcional, DROPI_SYNC_WC_STATUS) transiciona el estado de la orden WC.

El token WOOCOMERCE nunca sale del backend. Las órdenes Dropi sin `shop_order_id`
(creadas directo en Dropi) se ignoran: no tienen contraparte en la tienda.
"""

from datetime import UTC, datetime

import structlog

from app.clients import dropi
from app.clients.woocommerce import WCClientError, WCServerError, get_wc_client
from app.config import settings

logger = structlog.get_logger()

# Estados WC terminales: no se revierten a un estado intermedio aunque Dropi
# reporte algo "anterior" (p. ej. cierre manual en la tienda).
_WC_TERMINAL = {"completed", "cancelled", "refunded"}

# Mapeo explícito Dropi → WooCommerce (estado normalizado en MAYÚSCULAS).
_STATUS_MAP = {
    "PENDIENTE": "on-hold",
    "PENDIENTE CONFIRMACION": "on-hold",
    "NOVEDAD": "on-hold",
    "CONFIRMADO": "processing",
    "PREPARANDO": "processing",
    "EMPACADO": "processing",
    "GUIA GENERADA": "processing",
    "EN PROCESAMIENTO": "processing",
    "DESPACHADO": "processing",
    "ENVIADO": "processing",
    "EN TRANSITO": "processing",
    "EN REPARTO": "processing",
    "EN CAMINO": "processing",
    "EN BODEGA TRANSPORTADORA": "processing",
    "REEXPEDICION": "processing",
    "ENTREGADO": "completed",
    "DEVOLUCION": "refunded",
    "DEVUELTO": "refunded",
    "EN DEVOLUCION": "refunded",
    "CANCELADO": "cancelled",
    "ANULADO": "cancelled",
    "RECHAZADO": "cancelled",
}


def map_status(dropi_status: str | None) -> str | None:
    """Traduce un estado Dropi a estado WooCommerce. None si no se reconoce."""
    if not dropi_status:
        return None
    norm = " ".join(dropi_status.upper().replace("_", " ").split())
    if norm in _STATUS_MAP:
        return _STATUS_MAP[norm]
    # Heurística por subcadena para variantes no catalogadas.
    if "ENTREG" in norm:
        return "completed"
    if "DEVOL" in norm:
        return "refunded"
    if any(t in norm for t in ("CANCEL", "ANULAD", "RECHAZ")):
        return "cancelled"
    if any(
        t in norm
        for t in (
            "TRANSITO",
            "REPARTO",
            "DESPACH",
            "ENVIAD",
            "CAMINO",
            "BODEGA",
            "GUIA",
            "EMPACAD",
            "PREPARAND",
            "CONFIRMAD",
            "PROCES",
        )
    ):
        return "processing"
    if "PENDIENTE" in norm or "NOVEDAD" in norm:
        return "on-hold"
    return None


def build_update(wc_order: dict, f: dict) -> dict | None:
    """Construye el payload PUT para WC; None si no hay nada que cambiar."""
    metas = {m.get("key"): m.get("value") for m in wc_order.get("meta_data", [])}
    desired = {
        "_dropi_status": f.get("status") or "",
        "_dropi_carrier": f.get("carrier") or "",
        "_dropi_guide": f.get("guide") or "",
        "_dropi_guide_url": f.get("guide_url") or "",
        "_dropi_order_id": str(f.get("dropi_order_id") or ""),
    }
    meta_changed = any(str(metas.get(k, "")) != str(v) for k, v in desired.items())

    new_status = map_status(f.get("status")) if settings.DROPI_SYNC_WC_STATUS else None
    cur_status = wc_order.get("status")
    status_change = bool(new_status) and new_status != cur_status
    # No revertir un cierre terminal de la tienda a un estado intermedio.
    if status_change and cur_status in _WC_TERMINAL and new_status not in _WC_TERMINAL:
        status_change = False

    if not meta_changed and not status_change:
        return None

    desired["_dropi_synced_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    payload: dict = {"meta_data": [{"key": k, "value": v} for k, v in desired.items()]}
    if status_change:
        payload["status"] = new_status
    return payload


async def sync_orders() -> dict:
    """Cruza pedidos Dropi con WC y actualiza metadatos/estado. Idempotente."""
    if not settings.DROPI_WC_INTEGRATION_KEY:
        logger.warning("order_sync.skipped", reason="DROPI_WC_INTEGRATION_KEY vacío")
        return {"status": "skipped", "updated": 0, "skipped": 0, "failed": 0, "unlinked": 0}

    orders = await dropi.list_orders()
    fields = [dropi.order_sync_fields(o) for o in orders]
    linked = [f for f in fields if f.get("wc_order_id")]
    unlinked = len(fields) - len(linked)

    wc = await get_wc_client()
    updated = skipped = failed = 0
    for f in linked:
        wc_id = f["wc_order_id"]
        try:
            wc_order = await wc.get_order_raw(wc_id)
            payload = build_update(wc_order, f)
            if payload:
                await wc.update_order(wc_id, payload)
                updated += 1
            else:
                skipped += 1
        except WCClientError as exc:
            if exc.status_code == 404:
                skipped += 1  # la orden ya no existe en la tienda
            else:
                failed += 1
                logger.warning("order_sync.wc_client_error", wc_id=wc_id, error=str(exc))
        except WCServerError as exc:
            failed += 1
            logger.warning("order_sync.wc_server_error", wc_id=wc_id, error=str(exc))

    result = {
        "status": "ok",
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "unlinked": unlinked,
    }
    logger.info("order_sync.done", **result)
    return result
