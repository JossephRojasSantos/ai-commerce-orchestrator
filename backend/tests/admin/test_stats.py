"""Tests de agregación de stats (T010)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.admin.conftest import ADMIN_AUTH, make_order, make_product


def _wc_mock(orders, products):
    wc = MagicMock()
    wc.list_orders = AsyncMock(return_value=(orders, len(orders)))
    wc.list_products_raw = AsyncMock(return_value=products)
    return wc


@pytest.mark.asyncio
async def test_stats_aggregation(admin_client, no_cache):
    orders = [
        make_order(1, status="processing", total="49900"),
        make_order(
            2,
            status="completed",
            total="29900",
            payment="bacs",
            items=[
                {
                    "product_id": 70,
                    "name": "Delantal",
                    "quantity": 1,
                    "price": 29900,
                    "total": "29900",
                }
            ],
        ),
        make_order(3, status="cancelled", total="99999"),
    ]
    products = [make_product(84, dropi=True), make_product(70, price="29900", dropi=False)]
    wc = _wc_mock(orders, products)

    with (
        patch("app.services.admin.stats.get_wc_client", new_callable=AsyncMock, return_value=wc),
        patch(
            "app.services.admin.products_admin.get_wc_client",
            new_callable=AsyncMock,
            return_value=wc,
        ),
    ):
        resp = await admin_client.get("/v1/admin/stats?period=7d", headers=ADMIN_AUTH)

    assert resp.status_code == 200
    data = resp.json()
    # cancelada excluida de revenue
    assert data["revenue"] == 49900 + 29900
    assert data["orders"] == 2
    assert data["by_status"]["cancelled"] == 1
    assert data["by_payment"] == {"cod": 1, "other": 1}
    # ganancia: licuadora 49900-28000=21900 (dropi) + delantal 29900 completo (propio)
    assert data["estimated_profit"] == 21900 + 29900
    assert data["top_products"][0]["product_id"] in (84, 70)


@pytest.mark.asyncio
async def test_stats_empty_period(admin_client, no_cache):
    wc = _wc_mock([], [])
    with (
        patch("app.services.admin.stats.get_wc_client", new_callable=AsyncMock, return_value=wc),
        patch(
            "app.services.admin.products_admin.get_wc_client",
            new_callable=AsyncMock,
            return_value=wc,
        ),
    ):
        resp = await admin_client.get("/v1/admin/stats?period=today", headers=ADMIN_AUTH)
    data = resp.json()
    assert data["revenue"] == 0 and data["orders"] == 0 and data["avg_ticket"] == 0
