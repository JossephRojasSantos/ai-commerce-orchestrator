"""API del panel de administración — /v1/admin/* (feature 012).

Contrato completo en specs/012-admin-panel/contracts/admin-api.md.
Regla de oro: ningún endpoint devuelve meta_data crudo de WooCommerce
(contiene el token JWT de la integración Dropi).
"""

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from app.clients.woocommerce import WCClientError, WCServerError, get_wc_client
from app.core.admin_auth import (
    check_login_blocked,
    create_mfa_challenge,
    create_session,
    destroy_session,
    mfa_enabled,
    register_login_failure,
    require_admin_session,
    send_whatsapp_code,
    verify_password,
    verify_second_factor,
)
from app.services.admin import customers as customers_svc
from app.services.admin import products_admin
from app.services.admin import stats as stats_svc

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_ALLOWED_ORDER_STATUSES = {"processing", "completed", "cancelled", "on-hold"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ── Auth ─────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class MfaVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=4, max_length=10)


class MfaSendRequest(BaseModel):
    mfa_token: str = Field(min_length=1, max_length=200)


@router.post("/login")
async def login(req: LoginRequest, request: Request) -> dict:
    ip = _client_ip(request)
    if await check_login_blocked(ip):
        raise HTTPException(status_code=429, detail="too_many_attempts") from None

    if not verify_password(req.password):
        await register_login_failure(ip)
        raise HTTPException(status_code=401, detail="unauthorized") from None

    from app.config import settings

    # Primer factor OK. Si hay MFA configurado, exigir 2º factor.
    if mfa_enabled():
        mfa_token = await create_mfa_challenge(ip)
        from app.config import settings as s

        return {
            "mfa_required": True,
            "mfa_token": mfa_token,
            "whatsapp_available": bool(s.ADMIN_PHONE),
        }

    token = await create_session(ip)
    return {"token": token, "expires_in": settings.ADMIN_SESSION_TTL}


@router.post("/login/whatsapp")
async def login_whatsapp(req: MfaSendRequest) -> dict:
    """Respaldo: envía el código del 2º factor por WhatsApp al admin."""
    sent = await send_whatsapp_code(req.mfa_token)
    if not sent:
        raise HTTPException(status_code=400, detail="whatsapp_unavailable") from None
    return {"sent": True}


@router.post("/login/verify")
async def login_verify(req: MfaVerifyRequest) -> dict:
    """Valida TOTP o código WhatsApp y emite la sesión."""
    from app.config import settings

    token = await verify_second_factor(req.mfa_token, req.code)
    if token is None:
        raise HTTPException(status_code=401, detail="invalid_code") from None
    return {"token": token, "expires_in": settings.ADMIN_SESSION_TTL}


@router.post("/logout")
async def logout(token: str = Depends(require_admin_session)) -> dict:
    await destroy_session(token)
    return {"ok": True}


@router.get("/me")
async def me(_: str = Depends(require_admin_session)) -> dict:
    return {"ok": True}


@router.get("/config")
async def admin_config(_: str = Depends(require_admin_session)) -> dict:
    """Config no sensible para la UI (id de Clarity para el mapa de calor)."""
    from app.config import settings

    return {
        "clarity_project_id": settings.CLARITY_PROJECT_ID,
        "store_url": "https://tiendamagica.shop",
    }


# ── Stats (US1) ──────────────────────────────────────────────


@router.get("/stats")
async def stats(
    period: Literal["today", "7d", "30d"] = Query("7d"),
    _: str = Depends(require_admin_session),
) -> dict:
    try:
        return await stats_svc.get_stats(period)
    except (WCClientError, WCServerError):
        raise HTTPException(status_code=502, detail="store_unavailable") from None


# ── Pedidos (US2) ────────────────────────────────────────────


def _order_dto(o: dict) -> dict:
    billing = o.get("billing", {})
    metas = {m.get("key"): m.get("value") for m in o.get("meta_data", [])}
    dropi_meta = str(metas.get("_is_dropi_order", ""))
    return {
        "id": o.get("id"),
        "number": o.get("number"),
        "date": o.get("date_created", ""),
        "status": o.get("status", ""),
        "total": float(o.get("total") or 0),
        "payment_method": o.get("payment_method", ""),
        "payment_method_title": o.get("payment_method_title", ""),
        "customer_name": f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip(),
        "phone": billing.get("phone", ""),
        "city": billing.get("city", ""),
        "state": billing.get("state", ""),
        "dropi_synced": dropi_meta == "Yes",
        "dropi_order_id": str(metas.get("_dropi_order_id", "")) or None,
        "dropi_note": dropi_meta if dropi_meta and dropi_meta != "Yes" else None,
        "cod_modal": str(metas.get("_tm_cod_modal", "")) == "1",
        # Estado de fulfillment sincronizado desde Dropi (feature 016)
        "dropi_status": str(metas.get("_dropi_status", "")) or None,
        "dropi_carrier": str(metas.get("_dropi_carrier", "")) or None,
        "dropi_guide": str(metas.get("_dropi_guide", "")) or None,
        "dropi_guide_url": str(metas.get("_dropi_guide_url", "")) or None,
        "dropi_synced_at": str(metas.get("_dropi_synced_at", "")) or None,
    }


@router.get("/orders")
async def list_orders(
    status: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(require_admin_session),
) -> dict:
    try:
        wc = await get_wc_client()
        items, total = await wc.list_orders(
            status=status or "any", search=search, page=page, per_page=per_page
        )
    except (WCClientError, WCServerError):
        raise HTTPException(status_code=502, detail="store_unavailable") from None
    return {"items": [_order_dto(o) for o in items], "total": total, "page": page}


@router.post("/orders/sync", status_code=202)
async def orders_sync_trigger(_: str = Depends(require_admin_session)) -> dict:
    """Dispara la sincronización Dropi → WooCommerce en background (feature 016)."""
    from app.config import settings
    from app.core.tasks import spawn
    from app.workers.dropi_order_sync import SYNC_LOCK_KEY, run_sync_locked

    if not settings.DROPI_WC_INTEGRATION_KEY:
        raise HTTPException(status_code=503, detail="dropi_sync_disabled") from None
    if await _scout_lock_active(SYNC_LOCK_KEY):
        raise HTTPException(status_code=409, detail="already_running") from None
    spawn(run_sync_locked())
    return {"status": "running", "kind": "order_sync"}


@router.get("/dropi/orders")
async def list_dropi_orders(_: str = Depends(require_admin_session)) -> dict:
    """Lista los pedidos directamente desde Dropi (feature 017).

    Incluye los nativos de Dropi (sin contraparte en WooCommerce). `in_store`
    indica cuáles existen también en la tienda.
    """
    from app.clients import dropi
    from app.config import settings

    if not settings.DROPI_WC_INTEGRATION_KEY:
        raise HTTPException(status_code=503, detail="dropi_sync_disabled") from None
    try:
        orders = await dropi.list_orders()
    except Exception:  # noqa: BLE001 — fallo de Dropi (red/WAF/HTTP)
        raise HTTPException(status_code=502, detail="dropi_unavailable") from None
    items = [dropi.order_display_dto(o) for o in orders]
    in_store = sum(1 for i in items if i["in_store"])
    return {"items": items, "total": len(items), "in_store": in_store}


@router.get("/orders/{order_id}")
async def order_detail(order_id: int, _: str = Depends(require_admin_session)) -> dict:
    try:
        wc = await get_wc_client()
        o = await wc.get_order_raw(order_id)
        notes = await wc.get_order_notes(order_id)
    except WCClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="order_not_found") from None
        raise HTTPException(status_code=502, detail="store_unavailable") from None
    except WCServerError:
        raise HTTPException(status_code=502, detail="store_unavailable") from None

    dto = _order_dto(o)
    billing = o.get("billing", {})
    dto["address"] = billing.get("address_1", "")
    dto["address_extra"] = billing.get("address_2", "")
    dto["items"] = [
        {
            "product_id": i.get("product_id"),
            "name": i.get("name", ""),
            "quantity": i.get("quantity", 0),
            "price": float(i.get("price") or 0),
            "total": float(i.get("total") or 0),
        }
        for i in o.get("line_items", [])
    ]
    dto["notes"] = [{"date": n.get("date_created", ""), "note": n.get("note", "")} for n in notes]
    return dto


class OrderStatusUpdate(BaseModel):
    status: str


@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    req: OrderStatusUpdate,
    _: str = Depends(require_admin_session),
) -> dict:
    if req.status not in _ALLOWED_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="status_not_allowed") from None
    try:
        wc = await get_wc_client()
        updated = await wc.update_order(order_id, {"status": req.status})
    except WCClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="order_not_found") from None
        raise HTTPException(status_code=502, detail="store_unavailable") from None
    except WCServerError:
        raise HTTPException(status_code=502, detail="store_unavailable") from None

    await products_admin.invalidate_caches()
    logger.info("admin.order_status_changed", order_id=order_id, status=req.status)
    return _order_dto(updated)


# ── Clientes (US3) ───────────────────────────────────────────


@router.get("/customers")
async def list_customers(
    search: str = Query(""),
    _: str = Depends(require_admin_session),
) -> dict:
    try:
        items = await customers_svc.list_customers(search)
    except (WCClientError, WCServerError):
        raise HTTPException(status_code=502, detail="store_unavailable") from None
    return {"items": items}


# ── Productos (US4) ──────────────────────────────────────────


@router.get("/products")
async def list_products(_: str = Depends(require_admin_session)) -> dict:
    try:
        items = await products_admin.list_products()
    except (WCClientError, WCServerError):
        raise HTTPException(status_code=502, detail="store_unavailable") from None
    return {"items": items}


class ProductUpdate(BaseModel):
    price: float | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=50000)
    short_description: str | None = Field(default=None, max_length=10000)
    visible: bool | None = None
    # Config de secciones on/off (feature 019)
    landing: dict | None = None
    # Contenido editable de las secciones (_tm_* meta): benefits, includes, warranty, etc.
    tm_meta: dict | None = None


@router.get("/products/{product_id}")
async def product_detail(product_id: int, _: str = Depends(require_admin_session)) -> dict:
    try:
        return await products_admin.get_product_detail(product_id)
    except WCClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="product_not_found") from None
        raise HTTPException(status_code=502, detail="store_unavailable") from None
    except WCServerError:
        raise HTTPException(status_code=502, detail="store_unavailable") from None


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    req: ProductUpdate,
    _: str = Depends(require_admin_session),
) -> dict:
    if all(
        v is None
        for v in (
            req.price,
            req.stock,
            req.name,
            req.description,
            req.short_description,
            req.visible,
            req.landing,
            req.tm_meta,
        )
    ):
        raise HTTPException(status_code=422, detail="nothing_to_update") from None
    try:
        return await products_admin.update_product(
            product_id,
            price=req.price,
            stock=req.stock,
            name=req.name,
            description=req.description,
            short_description=req.short_description,
            visible=req.visible,
            landing=req.landing,
            tm_meta=req.tm_meta,
        )
    except WCClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="product_not_found") from None
        raise HTTPException(status_code=502, detail="store_unavailable") from None
    except WCServerError:
        raise HTTPException(status_code=502, detail="store_unavailable") from None


@router.post("/media", status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    _: str = Depends(require_admin_session),
) -> dict:
    """Sube una imagen suelta (p. ej. foto de reseña) y devuelve su URL pública."""
    from app.services.admin import media_store

    if file.content_type not in media_store.ALLOWED_MIME:
        raise HTTPException(status_code=422, detail="formato_no_soportado") from None
    content = await file.read()
    if len(content) > media_store.MAX_BYTES:
        raise HTTPException(status_code=413, detail="imagen_muy_grande") from None
    media_id = await media_store.store_image(content, file.content_type)
    return {"url": media_store.public_url(media_id)}


@router.post("/products/{product_id}/image", status_code=201)
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    _: str = Depends(require_admin_session),
) -> dict:
    from app.services.admin import media_store

    if file.content_type not in media_store.ALLOWED_MIME:
        raise HTTPException(status_code=422, detail="formato_no_soportado") from None
    content = await file.read()
    if len(content) > media_store.MAX_BYTES:
        raise HTTPException(status_code=413, detail="imagen_muy_grande") from None
    try:
        return await products_admin.add_product_image(product_id, content, file.content_type)
    except WCClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="product_not_found") from None
        raise HTTPException(status_code=502, detail=f"woocommerce_error: {exc.message}") from None
    except WCServerError:
        raise HTTPException(status_code=502, detail="store_unavailable") from None


@router.delete("/products/{product_id}/image/{image_id}")
async def delete_product_image(
    product_id: int, image_id: int, _: str = Depends(require_admin_session)
) -> dict:
    try:
        return await products_admin.delete_product_image(product_id, image_id)
    except (WCClientError, WCServerError):
        raise HTTPException(status_code=502, detail="store_unavailable") from None


# ── Consumo IA (feature 013, US1) ───────────────────────────


@router.get("/ai/usage")
async def ai_usage_summary(
    period: Literal["today", "7d", "30d"] = Query("7d"),
    _: str = Depends(require_admin_session),
) -> dict:
    from app.services.admin import ai_usage as ai_usage_svc

    return await ai_usage_svc.get_usage_summary(period)


# ── Bandeja WhatsApp (feature 013, US2/US3) ──────────────────


class WaReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("/wa/conversations")
async def wa_conversations(_: str = Depends(require_admin_session)) -> dict:
    from app.services import wa_inbox

    return {"items": await wa_inbox.list_conversations()}


@router.get("/wa/conversations/{phone}")
async def wa_thread(phone: str, _: str = Depends(require_admin_session)) -> dict:
    from app.services import wa_inbox

    thread = await wa_inbox.get_thread(phone)
    if thread is None:
        raise HTTPException(status_code=404, detail="conversation_not_found") from None
    return thread


@router.post("/wa/conversations/{phone}/reply")
async def wa_reply(
    phone: str,
    req: WaReplyRequest,
    _: str = Depends(require_admin_session),
) -> dict:
    from app.integrations.whatsapp.client import send_text_message
    from app.services import wa_inbox

    thread = await wa_inbox.get_thread(phone)
    if thread is None:
        raise HTTPException(status_code=404, detail="conversation_not_found") from None
    if not thread["window_open"]:
        raise HTTPException(status_code=409, detail="window_closed") from None

    result = await send_text_message(wa_inbox.normalize_phone(phone), req.text)
    delivered = result.status == "sent"
    await wa_inbox.record_outgoing(phone, req.text, author="admin", delivered=delivered)

    if not delivered:
        raise HTTPException(status_code=502, detail="whatsapp_send_failed") from None

    conv = await wa_inbox.set_mode(phone, "human")
    logger.info("admin.wa_reply_sent", phone=phone)
    return {
        "ok": True,
        "mode": "human",
        "human_until": conv.human_until.isoformat() if conv and conv.human_until else None,
    }


# Tipos de adjunto permitidos desde el inbox admin (imagen + documento).
_WA_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
_WA_DOC_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
}


@router.post("/wa/conversations/{phone}/reply-media")
async def wa_reply_media(
    phone: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    _: str = Depends(require_admin_session),
) -> dict:
    from app.config import settings
    from app.integrations.whatsapp.client import send_media_message, upload_media
    from app.services import wa_inbox

    mime = file.content_type or ""
    if mime in _WA_IMAGE_MIMES:
        media_type = "image"
    elif mime in _WA_DOC_MIMES:
        media_type = "document"
    else:
        raise HTTPException(status_code=415, detail="unsupported_media_type") from None

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty_file") from None
    if len(data) > settings.WA_MEDIA_MAX_BYTES:
        raise HTTPException(status_code=413, detail="file_too_large") from None

    thread = await wa_inbox.get_thread(phone)
    if thread is None:
        raise HTTPException(status_code=404, detail="conversation_not_found") from None
    if not thread["window_open"]:
        raise HTTPException(status_code=409, detail="window_closed") from None

    media_id = await upload_media(data, mime, file.filename or "adjunto")
    if not media_id:
        raise HTTPException(status_code=502, detail="media_upload_failed") from None

    result = await send_media_message(
        wa_inbox.normalize_phone(phone),
        media_type=media_type,
        media_id=media_id,
        caption=caption or None,
        filename=file.filename,
    )
    delivered = result.status == "sent"
    await wa_inbox.record_outgoing(
        phone,
        caption or f"[{'imagen' if media_type == 'image' else 'documento'}]",
        author="admin",
        delivered=delivered,
        wa_message_id=result.message_id or None,
        media_id=media_id,
        media_type=media_type,
        media_mime=mime,
        media_filename=file.filename,
    )
    if not delivered:
        raise HTTPException(status_code=502, detail="whatsapp_send_failed") from None

    conv = await wa_inbox.set_mode(phone, "human")
    logger.info("admin.wa_reply_media_sent", phone=phone, media_type=media_type)
    return {
        "ok": True,
        "mode": "human",
        "human_until": conv.human_until.isoformat() if conv and conv.human_until else None,
    }


@router.get("/wa/media/{media_id}")
async def wa_media_proxy(media_id: str, _: str = Depends(require_admin_session)) -> Response:
    """Proxy autenticado: descarga un adjunto de la Graph API para verlo en el inbox."""
    from app.integrations.whatsapp.media import download_media

    data, mime = await download_media(media_id)
    if not data:
        raise HTTPException(status_code=404, detail="media_not_found") from None
    return Response(
        content=data,
        media_type=mime or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/wa/conversations/{phone}/resume-bot")
async def wa_resume_bot(phone: str, _: str = Depends(require_admin_session)) -> dict:
    from app.services import wa_inbox

    conv = await wa_inbox.set_mode(phone, "bot")
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation_not_found") from None
    logger.info("admin.wa_bot_resumed", phone=phone)
    return {"ok": True, "mode": "bot"}


# ── Métricas IA (US5) ────────────────────────────────────────


@router.get("/ai/metrics")
async def ai_metrics(_: str = Depends(require_admin_session)) -> dict:
    from app.db.base import AsyncSessionLocal
    from app.models.conversation import Conversation, Message

    async with AsyncSessionLocal() as db:
        conversations = (await db.execute(select(func.count(Conversation.id)))).scalar() or 0
        messages = (await db.execute(select(func.count(Message.id)))).scalar() or 0

        intents: dict[str, int] = {}
        result = await db.execute(select(Message.metadata_).where(Message.role == "assistant"))
        for (meta,) in result.all():
            intent = (meta or {}).get("intent") or "other"
            intents[intent] = intents.get(intent, 0) + 1

    return {"conversations": conversations, "messages": messages, "intents": intents}


@router.get("/ai/conversations")
async def ai_conversations(
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(require_admin_session),
) -> dict:
    from app.db.base import AsyncSessionLocal
    from app.models.conversation import Conversation, Message

    async with AsyncSessionLocal() as db:
        convs = (
            (
                await db.execute(
                    select(Conversation).order_by(desc(Conversation.updated_at)).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        items = []
        for c in convs:
            count = (
                await db.execute(
                    select(func.count(Message.id)).where(Message.conversation_id == c.id)
                )
            ).scalar() or 0
            first = (
                await db.execute(
                    select(Message.content)
                    .where(Message.conversation_id == c.id, Message.role == "user")
                    .order_by(Message.created_at)
                    .limit(1)
                )
            ).scalar()
            items.append(
                {
                    "session_id": str(c.session_id),
                    "date": c.created_at.isoformat() if c.created_at else "",
                    "messages": count,
                    "first_message": (first or "")[:120],
                }
            )
    return {"items": items}


@router.get("/ai/conversations/{session_id}")
async def ai_conversation_detail(session_id: str, _: str = Depends(require_admin_session)) -> dict:
    import uuid as uuid_mod

    from app.db.base import AsyncSessionLocal
    from app.models.conversation import Conversation, Message

    try:
        sid = uuid_mod.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="conversation_not_found") from None

    async with AsyncSessionLocal() as db:
        conv = (
            await db.execute(select(Conversation).where(Conversation.session_id == sid))
        ).scalar_one_or_none()
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation_not_found") from None
        msgs = (
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at)
                )
            )
            .scalars()
            .all()
        )
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "date": m.created_at.isoformat() if m.created_at else "",
                "intent": (m.metadata_ or {}).get("intent"),
            }
            for m in msgs
        ],
    }


# --- Product Scout (feature 014) ---


async def _scout_lock_active(key: str) -> bool:
    import redis.asyncio as aioredis

    from app.config import settings

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        return bool(await r.exists(key))
    finally:
        await r.aclose()


@router.get("/scout/ranking")
async def scout_ranking(
    category: str | None = None,
    period: Literal["today", "7d", "30d"] = "7d",
    include_nonviable: bool = False,
    search: str | None = None,
    _: str = Depends(require_admin_session),
) -> dict:
    from app.db.base import AsyncSessionLocal
    from app.services.admin import scout as scout_svc

    async with AsyncSessionLocal() as db:
        return await scout_svc.get_ranking(
            db,
            category=category,
            period=period,
            include_nonviable=include_nonviable,
            search=search,
        )


@router.get("/scout/runs")
async def scout_runs(
    limit: int = Query(default=10, le=50),
    _: str = Depends(require_admin_session),
) -> dict:
    from app.db.base import AsyncSessionLocal
    from app.services.admin import scout as scout_svc

    async with AsyncSessionLocal() as db:
        return {"runs": await scout_svc.list_runs(db, limit=limit)}


@router.post("/scout/ingest", status_code=202)
async def scout_ingest_trigger(_: str = Depends(require_admin_session)) -> dict:
    from app.core.tasks import spawn
    from app.workers.scout_ingest import INGEST_LOCK_KEY, run_ingest_locked

    if await _scout_lock_active(INGEST_LOCK_KEY):
        raise HTTPException(status_code=409, detail="already_running") from None
    spawn(run_ingest_locked())
    return {"status": "running", "kind": "ingest"}


@router.post("/scout/score", status_code=202)
async def scout_score_trigger(_: str = Depends(require_admin_session)) -> dict:
    from app.core.tasks import spawn
    from app.services.admin.scout_score import SCORE_LOCK_KEY, run_scoring_locked

    if await _scout_lock_active(SCORE_LOCK_KEY):
        raise HTTPException(status_code=409, detail="already_running") from None
    spawn(run_scoring_locked())
    return {"status": "running", "kind": "score"}


@router.post("/scout/import/{dropi_product_id}", status_code=201)
async def scout_import(dropi_product_id: int, _: str = Depends(require_admin_session)) -> dict:
    from app.services.admin.scout_import import import_product

    try:
        result = await import_product(dropi_product_id)
    except (WCClientError, WCServerError) as exc:
        raise HTTPException(status_code=502, detail=f"woocommerce_error: {exc.message}") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return result


@router.get("/scout/demand")
async def scout_demand(_: str = Depends(require_admin_session)) -> dict:
    from app.db.base import AsyncSessionLocal
    from app.services.admin.scout_demand import list_unmet_demand

    async with AsyncSessionLocal() as db:
        return await list_unmet_demand(db)


@router.post("/scout/demand/refresh", status_code=202)
async def scout_demand_refresh(_: str = Depends(require_admin_session)) -> dict:
    from app.core.tasks import spawn
    from app.services.admin.scout_demand import DEMAND_LOCK_KEY, run_demand_locked

    if await _scout_lock_active(DEMAND_LOCK_KEY):
        raise HTTPException(status_code=409, detail="already_running") from None
    spawn(run_demand_locked())
    return {"status": "running", "kind": "demand"}
