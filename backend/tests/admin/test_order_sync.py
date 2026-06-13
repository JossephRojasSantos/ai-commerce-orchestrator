"""Tests del sync de pedidos Dropi → WooCommerce (feature 016)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from app.clients import dropi
from app.clients.woocommerce import WCClientError, WCServerError
from app.config import settings
from app.services.admin import order_sync
from app.workers import dropi_order_sync


def _dropi_order(dropi_id, wc_id, status, carrier="COORDINADORA", guide=None, guide_url=None):
    return {
        "id": dropi_id,
        "shop_order_id": wc_id,
        "status": status,
        "distribution_company": {"id": 5, "name": carrier},
        "shipping_guide": guide,
        "guia_urls3": guide_url,
        "total_order": 130000,
        "updated_at": "2026-06-13T07:15:15",
    }


# ── cliente ──
@pytest.mark.asyncio
@respx.mock
async def test_list_orders_uses_wc_token_and_result_number():
    route = respx.get(f"{settings.DROPI_API_BASE}/orders/myorders").mock(
        return_value=httpx.Response(
            200, json={"isSuccess": True, "objects": [_dropi_order(1, 97, "PENDIENTE")]}
        )
    )
    with patch.object(settings, "DROPI_WC_INTEGRATION_KEY", "wc-tok"):
        out = await dropi.list_orders(result_number=50)
    assert len(out) == 1
    req = route.calls[0].request
    assert req.headers["dropi-integration-key"] == "wc-tok"
    assert req.headers["user-agent"] == settings.DROPI_USER_AGENT  # WAF
    assert req.url.params["result_number"] == "50"


@pytest.mark.asyncio
@respx.mock
async def test_list_orders_clamps_result_number_to_100():
    # Dropi rechaza result_number alto con 400; el cliente lo topa en 100.
    route = respx.get(f"{settings.DROPI_API_BASE}/orders/myorders").mock(
        return_value=httpx.Response(200, json={"isSuccess": True, "objects": []})
    )
    with patch.object(settings, "DROPI_WC_INTEGRATION_KEY", "wc-tok"):
        await dropi.list_orders(result_number=500)
    assert route.calls[0].request.url.params["result_number"] == "100"


@pytest.mark.asyncio
@respx.mock
async def test_list_orders_error_raises():
    respx.get(f"{settings.DROPI_API_BASE}/orders/myorders").mock(
        return_value=httpx.Response(200, json={"isSuccess": False, "status": 401})
    )
    with pytest.raises(RuntimeError):
        await dropi.list_orders()


def test_order_sync_fields_extracts_join_key():
    f = dropi.order_sync_fields(_dropi_order(78500204, 97, "ENTREGADO", guide="ABC123"))
    assert f["wc_order_id"] == 97
    assert f["dropi_order_id"] == 78500204
    assert f["status"] == "ENTREGADO"
    assert f["carrier"] == "COORDINADORA"
    assert f["guide"] == "ABC123"


# ── mapeo de estado ──
@pytest.mark.parametrize(
    "dropi_status,expected",
    [
        ("PENDIENTE", "on-hold"),
        ("PENDIENTE CONFIRMACION", "on-hold"),
        ("NOVEDAD", "on-hold"),
        ("GUIA_GENERADA", "processing"),
        ("EN TRANSITO", "processing"),
        ("ENVIADO", "processing"),
        ("ENTREGADO", "completed"),
        ("DEVOLUCION", "refunded"),
        ("CANCELADO", "cancelled"),
        ("RECHAZADO", "cancelled"),
        ("ESTADO RARO NO MAPEADO", None),
        ("", None),
        (None, None),
    ],
)
def test_map_status(dropi_status, expected):
    assert order_sync.map_status(dropi_status) == expected


# ── build_update ──
def _wc_order(status="on-hold", metas=None):
    md = [{"key": k, "value": v} for k, v in (metas or {}).items()]
    return {"id": 97, "status": status, "meta_data": md}


def test_build_update_new_order_sets_meta_and_status():
    f = dropi.order_sync_fields(_dropi_order(1, 97, "ENTREGADO"))
    payload = order_sync.build_update(_wc_order(status="processing"), f)
    assert payload is not None
    metas = {m["key"]: m["value"] for m in payload["meta_data"]}
    assert metas["_dropi_status"] == "ENTREGADO"
    assert metas["_dropi_carrier"] == "COORDINADORA"
    assert "_dropi_synced_at" in metas
    assert payload["status"] == "completed"


def test_build_update_idempotent_returns_none():
    f = dropi.order_sync_fields(_dropi_order(1, 97, "PENDIENTE"))
    existing = {
        "_dropi_status": "PENDIENTE",
        "_dropi_carrier": "COORDINADORA",
        "_dropi_guide": "",
        "_dropi_guide_url": "",
        "_dropi_order_id": "1",
    }
    # WC ya está en on-hold (mapeo de PENDIENTE) y los metadatos coinciden
    assert order_sync.build_update(_wc_order(status="on-hold", metas=existing), f) is None


def test_build_update_does_not_revert_terminal_wc_status():
    # Dropi dice PENDIENTE pero la tienda ya cerró la orden como completed
    f = dropi.order_sync_fields(_dropi_order(1, 97, "PENDIENTE"))
    payload = order_sync.build_update(_wc_order(status="completed"), f)
    # se escriben metadatos pero NO se revierte el estado
    assert payload is not None
    assert "status" not in payload


def test_build_update_meta_only_when_status_sync_disabled():
    f = dropi.order_sync_fields(_dropi_order(1, 97, "ENTREGADO"))
    with patch.object(settings, "DROPI_SYNC_WC_STATUS", False):
        payload = order_sync.build_update(_wc_order(status="processing"), f)
    assert payload is not None
    assert "status" not in payload


# ── sync_orders (orquestación) ──
@pytest.mark.asyncio
async def test_sync_orders_skips_unlinked_and_updates_linked():
    orders = [
        _dropi_order(78609372, None, "PENDIENTE"),  # sin shop_order_id → unlinked
        _dropi_order(78500204, 97, "ENTREGADO"),  # linked → update
    ]
    fake_wc = AsyncMock()
    fake_wc.get_order_raw.return_value = _wc_order(status="processing")
    fake_wc.update_order.return_value = {}
    with (
        patch.object(settings, "DROPI_WC_INTEGRATION_KEY", "wc-tok"),
        patch.object(order_sync.dropi, "list_orders", AsyncMock(return_value=orders)),
        patch.object(order_sync, "get_wc_client", AsyncMock(return_value=fake_wc)),
    ):
        result = await order_sync.sync_orders()
    assert result["unlinked"] == 1
    assert result["updated"] == 1
    fake_wc.update_order.assert_awaited_once()
    args = fake_wc.update_order.await_args.args
    assert args[0] == 97 and args[1]["status"] == "completed"


@pytest.mark.asyncio
async def test_sync_orders_disabled_when_no_token():
    with patch.object(settings, "DROPI_WC_INTEGRATION_KEY", ""):
        result = await order_sync.sync_orders()
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_sync_orders_counts_wc_errors():
    orders = [
        _dropi_order(1, 97, "ENTREGADO"),  # 404 → skipped
        _dropi_order(2, 98, "ENTREGADO"),  # 500 client → failed
        _dropi_order(3, 99, "ENTREGADO"),  # server error → failed
    ]
    fake_wc = AsyncMock()
    fake_wc.get_order_raw.side_effect = [
        WCClientError(404, "not found"),
        WCClientError(500, "boom"),
        WCServerError(503, "down"),
    ]
    with (
        patch.object(settings, "DROPI_WC_INTEGRATION_KEY", "wc-tok"),
        patch.object(order_sync.dropi, "list_orders", AsyncMock(return_value=orders)),
        patch.object(order_sync, "get_wc_client", AsyncMock(return_value=fake_wc)),
    ):
        result = await order_sync.sync_orders()
    assert result["skipped"] == 1
    assert result["failed"] == 2
    fake_wc.update_order.assert_not_awaited()


# ── heurística de mapeo (variantes no catalogadas) ──
@pytest.mark.parametrize(
    "dropi_status,expected",
    [
        ("ENTREGA PARCIAL", "completed"),
        ("DEVOLUCION PARCIAL", "refunded"),
        ("PEDIDO ANULADO", "cancelled"),
        ("EN PROCESO LOGISTICO", "processing"),
        ("PENDIENTE DE ALGO", "on-hold"),
    ],
)
def test_map_status_heuristics(dropi_status, expected):
    assert order_sync.map_status(dropi_status) == expected


# ── worker (lock Redis) ──
class _FakeRedis:
    def __init__(self, acquired):
        self._acquired = acquired
        self.deleted = False

    async def set(self, *a, **kw):
        return self._acquired

    async def delete(self, *a):
        self.deleted = True

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_run_sync_locked_blocks_when_locked():
    with patch("redis.asyncio.from_url", return_value=_FakeRedis(acquired=None)):
        assert await dropi_order_sync.run_sync_locked() is None


@pytest.mark.asyncio
async def test_run_sync_locked_runs_and_releases():
    r = _FakeRedis(acquired=True)
    with (
        patch("redis.asyncio.from_url", return_value=r),
        patch.object(dropi_order_sync, "sync_orders", AsyncMock(return_value={"status": "ok"})),
    ):
        result = await dropi_order_sync.run_sync_locked()
    assert result == {"status": "ok"}
    assert r.deleted is True  # lock liberado


# ── endpoint POST /v1/admin/orders/sync ──
@pytest.mark.asyncio
async def test_orders_sync_endpoint_503_when_disabled(admin_client):
    with patch.object(settings, "DROPI_WC_INTEGRATION_KEY", ""):
        resp = await admin_client.post("/v1/admin/orders/sync")
    assert resp.status_code == 503
    assert resp.json()["message"] == "dropi_sync_disabled"


@pytest.mark.asyncio
async def test_orders_sync_endpoint_409_when_locked(admin_client):
    with (
        patch.object(settings, "DROPI_WC_INTEGRATION_KEY", "wc-tok"),
        patch("app.routers.admin._scout_lock_active", new=AsyncMock(return_value=True)),
    ):
        resp = await admin_client.post("/v1/admin/orders/sync")
    assert resp.status_code == 409
    assert resp.json()["message"] == "already_running"


@pytest.mark.asyncio
async def test_orders_sync_endpoint_202_launches(admin_client):
    launched = {}

    async def fake_run():
        launched["yes"] = True

    with (
        patch.object(settings, "DROPI_WC_INTEGRATION_KEY", "wc-tok"),
        patch("app.routers.admin._scout_lock_active", new=AsyncMock(return_value=False)),
        patch("app.workers.dropi_order_sync.run_sync_locked", side_effect=fake_run),
    ):
        resp = await admin_client.post("/v1/admin/orders/sync")
        import asyncio

        await asyncio.sleep(0)
    assert resp.status_code == 202
    assert resp.json()["status"] == "running"
    assert launched.get("yes") is True
