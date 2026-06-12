"""Cobertura de rutas de error del router admin: WC caído (502) y 404."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.clients.woocommerce import WCClientError, WCServerError

from tests.admin.conftest import ADMIN_AUTH


def _wc_raising(exc):
    wc = MagicMock()
    for m in ("list_orders", "get_order_raw", "get_order_notes", "update_order"):
        setattr(wc, m, AsyncMock(side_effect=exc))
    return wc


@pytest.mark.asyncio
async def test_stats_store_unavailable(admin_client, no_cache):
    with (
        patch(
            "app.services.admin.stats.get_wc_client",
            new_callable=AsyncMock,
            side_effect=WCServerError(503, "down"),
        ),
    ):
        resp = await admin_client.get("/v1/admin/stats?period=7d", headers=ADMIN_AUTH)
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_orders_store_unavailable(admin_client):
    wc = _wc_raising(WCServerError(500, "boom"))
    with patch("app.routers.admin.get_wc_client", new_callable=AsyncMock, return_value=wc):
        resp = await admin_client.get("/v1/admin/orders", headers=ADMIN_AUTH)
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_order_detail_404(admin_client):
    wc = _wc_raising(WCClientError(404, "not found"))
    with patch("app.routers.admin.get_wc_client", new_callable=AsyncMock, return_value=wc):
        resp = await admin_client.get("/v1/admin/orders/999", headers=ADMIN_AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_order_status_404_and_502(admin_client, no_cache):
    wc = _wc_raising(WCClientError(404, "nf"))
    with patch("app.routers.admin.get_wc_client", new_callable=AsyncMock, return_value=wc):
        r404 = await admin_client.put(
            "/v1/admin/orders/999/status", json={"status": "completed"}, headers=ADMIN_AUTH
        )
    assert r404.status_code == 404

    wc2 = _wc_raising(WCServerError(500, "x"))
    with patch("app.routers.admin.get_wc_client", new_callable=AsyncMock, return_value=wc2):
        r502 = await admin_client.put(
            "/v1/admin/orders/1/status", json={"status": "completed"}, headers=ADMIN_AUTH
        )
    assert r502.status_code == 502


@pytest.mark.asyncio
async def test_customers_and_products_store_unavailable(admin_client, no_cache):
    with patch(
        "app.services.admin.customers.get_wc_client",
        new_callable=AsyncMock,
        side_effect=WCClientError(503, "down"),
    ):
        rc = await admin_client.get("/v1/admin/customers", headers=ADMIN_AUTH)
    assert rc.status_code == 502

    with patch(
        "app.services.admin.products_admin.get_wc_client",
        new_callable=AsyncMock,
        side_effect=WCServerError(503, "down"),
    ):
        rp = await admin_client.get("/v1/admin/products", headers=ADMIN_AUTH)
    assert rp.status_code == 502


@pytest.mark.asyncio
async def test_product_update_404_and_empty(admin_client, no_cache):
    wc = MagicMock()
    wc.update_product = AsyncMock(side_effect=WCClientError(404, "nf"))
    with patch(
        "app.services.admin.products_admin.get_wc_client",
        new_callable=AsyncMock,
        return_value=wc,
    ):
        r404 = await admin_client.put(
            "/v1/admin/products/999", json={"price": 5000}, headers=ADMIN_AUTH
        )
    assert r404.status_code == 404

    empty = await admin_client.put("/v1/admin/products/1", json={}, headers=ADMIN_AUTH)
    assert empty.status_code == 422


@pytest.mark.asyncio
async def test_whatsapp_send_fails_when_no_phone(admin_client):
    # send_whatsapp_code devuelve False (sin ADMIN_PHONE / challenge inválido) → 400
    with patch("app.routers.admin.send_whatsapp_code", new_callable=AsyncMock, return_value=False):
        resp = await admin_client.post("/v1/admin/login/whatsapp", json={"mfa_token": "x"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_invalid_code_returns_401(admin_client):
    with patch("app.routers.admin.verify_second_factor", new_callable=AsyncMock, return_value=None):
        resp = await admin_client.post(
            "/v1/admin/login/verify", json={"mfa_token": "x", "code": "000000"}
        )
    assert resp.status_code == 401
