"""Tests de gestión de pedidos (T013)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.admin.conftest import ADMIN_AUTH, make_order


@pytest.mark.asyncio
async def test_list_orders_dto_and_dropi_flags(admin_client):
    orders = [
        make_order(
            97,
            metas={"_is_dropi_order": "Yes", "_dropi_order_id": "78500204", "_tm_cod_modal": "1"},
        ),
        make_order(96, metas={"_is_dropi_order": "Dropi sync error: monto a ganar <= 0"}),
    ]
    wc = MagicMock()
    wc.list_orders = AsyncMock(return_value=(orders, 2))
    with patch("app.routers.admin.get_wc_client", new_callable=AsyncMock, return_value=wc):
        resp = await admin_client.get("/v1/admin/orders", headers=ADMIN_AUTH)

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["dropi_synced"] is True
    assert items[0]["dropi_order_id"] == "78500204"
    assert items[0]["cod_modal"] is True
    assert items[1]["dropi_synced"] is False
    assert "monto a ganar" in items[1]["dropi_note"]
    # sin meta crudo en la respuesta
    assert "meta_data" not in items[0]


@pytest.mark.asyncio
async def test_order_detail_includes_items_and_notes(admin_client):
    wc = MagicMock()
    wc.get_order_raw = AsyncMock(return_value=make_order(95))
    wc.get_order_notes = AsyncMock(
        return_value=[{"date_created": "2026-06-11", "note": "WhatsApp COD enviado"}]
    )
    with patch("app.routers.admin.get_wc_client", new_callable=AsyncMock, return_value=wc):
        resp = await admin_client.get("/v1/admin/orders/95", headers=ADMIN_AUTH)

    data = resp.json()
    assert data["items"][0]["product_id"] == 84
    assert data["notes"][0]["note"].startswith("WhatsApp")
    assert data["address"] == "Calle 1"


@pytest.mark.asyncio
async def test_update_status_valid_and_invalid(admin_client, no_cache):
    wc = MagicMock()
    wc.update_order = AsyncMock(return_value=make_order(95, status="completed"))
    with patch("app.routers.admin.get_wc_client", new_callable=AsyncMock, return_value=wc):
        ok = await admin_client.put(
            "/v1/admin/orders/95/status", json={"status": "completed"}, headers=ADMIN_AUTH
        )
        bad = await admin_client.put(
            "/v1/admin/orders/95/status", json={"status": "trash"}, headers=ADMIN_AUTH
        )

    assert ok.status_code == 200 and ok.json()["status"] == "completed"
    assert bad.status_code == 422
