"""Tests de productos y margen (T019)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.admin.products_admin import _extract_supplier_cost

from tests.admin.conftest import ADMIN_AUTH, DROPI_META_SERIALIZED, make_product


def test_extract_supplier_cost_from_serialized_meta():
    meta = [{"key": "_dropi_product", "value": DROPI_META_SERIALIZED}]
    assert _extract_supplier_cost(meta) == 28000.0
    assert _extract_supplier_cost([]) is None


@pytest.mark.asyncio
async def test_products_margin_and_no_raw_meta(admin_client, no_cache):
    products = [
        make_product(84, price="49900", dropi=True),  # margen 49900-28000-12000 = 9900
        make_product(85, price="30000", dropi=True),  # margen -10000 → alerta
        make_product(70, price="29900", dropi=False),  # propio
    ]
    wc = MagicMock()
    wc.list_products_raw = AsyncMock(return_value=products)
    with patch(
        "app.services.admin.products_admin.get_wc_client",
        new_callable=AsyncMock,
        return_value=wc,
    ):
        resp = await admin_client.get("/v1/admin/products", headers=ADMIN_AUTH)

    items = {p["id"]: p for p in resp.json()["items"]}
    assert items[84]["margin"] == 9900 and items[84]["margin_alert"] is False
    assert items[84]["price_floor"] == 40000  # costo 28000 + flete 12000 + margen mín 0
    assert items[85]["margin_alert"] is True
    assert items[70]["origin"] == "own" and items[70]["supplier_cost"] is None


@pytest.mark.asyncio
async def test_price_floor_with_min_margin(admin_client, no_cache):
    """Con margen mínimo, un producto rentable pero bajo el piso se marca en alerta."""
    from app.config import settings

    products = [make_product(84, price="45000", dropi=True)]  # margen 5000 (>0 pero < mín)
    wc = MagicMock()
    wc.list_products_raw = AsyncMock(return_value=products)
    with (
        patch.object(settings, "ADMIN_MIN_MARGIN", 8000),
        patch(
            "app.services.admin.products_admin.get_wc_client",
            new_callable=AsyncMock,
            return_value=wc,
        ),
    ):
        resp = await admin_client.get("/v1/admin/products", headers=ADMIN_AUTH)

    p = {x["id"]: x for x in resp.json()["items"]}[84]
    assert p["price_floor"] == 48000  # 28000 + 12000 + 8000
    assert p["margin"] == 5000 and p["margin_alert"] is True  # 45000 < 48000
    # el meta crudo (con token Dropi) jamás sale
    body = resp.text
    assert "SECRET-JWT-NO-EXPONER" not in body
    assert "meta_data" not in body


@pytest.mark.asyncio
async def test_product_update_validation_and_put(admin_client, no_cache):
    wc = MagicMock()
    wc.update_product = AsyncMock(return_value=make_product(84, price="55000"))
    with patch(
        "app.services.admin.products_admin.get_wc_client",
        new_callable=AsyncMock,
        return_value=wc,
    ):
        ok = await admin_client.put(
            "/v1/admin/products/84", json={"price": 55000}, headers=ADMIN_AUTH
        )
        empty = await admin_client.put("/v1/admin/products/84", json={}, headers=ADMIN_AUTH)
        neg = await admin_client.put(
            "/v1/admin/products/84", json={"price": -5}, headers=ADMIN_AUTH
        )

    assert ok.status_code == 200 and ok.json()["price"] == 55000.0
    wc.update_product.assert_awaited_once_with(84, {"regular_price": "55000"})
    assert empty.status_code == 422
    assert neg.status_code == 422
