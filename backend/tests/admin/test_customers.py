"""Tests de clientes derivados (T016)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.admin.conftest import ADMIN_AUTH, make_order


@pytest.mark.asyncio
async def test_customers_aggregated_by_phone(admin_client, no_cache):
    orders = [
        make_order(3, phone="+57 300 123 4567", total="49900", date="2026-06-12T10:00:00"),
        make_order(2, phone="3001234567", total="29900", date="2026-06-10T10:00:00"),
        make_order(1, phone="3009999999", total="15000", status="cancelled"),
    ]
    wc = MagicMock()
    wc.list_orders = AsyncMock(return_value=(orders, 3))
    with patch(
        "app.services.admin.customers.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.get("/v1/admin/customers", headers=ADMIN_AUTH)

    items = resp.json()["items"]
    # el cliente cancelado-único no aparece; los dos pedidos del mismo teléfono se agregan
    assert len(items) == 1
    c = items[0]
    assert c["phone"] == "3001234567"
    assert c["orders_count"] == 2
    assert c["total_spent"] == 49900 + 29900


@pytest.mark.asyncio
async def test_customers_search(admin_client, no_cache):
    orders = [
        make_order(1, phone="3001234567", name=("Maria", "Paula")),
        make_order(2, phone="3166235026", name=("Josseph", "Rojas")),
    ]
    wc = MagicMock()
    wc.list_orders = AsyncMock(return_value=(orders, 2))
    with patch(
        "app.services.admin.customers.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.get("/v1/admin/customers?search=316", headers=ADMIN_AUTH)

    items = resp.json()["items"]
    assert len(items) == 1 and items[0]["phone"] == "3166235026"
