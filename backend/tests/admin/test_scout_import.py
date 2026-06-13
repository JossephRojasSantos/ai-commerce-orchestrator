"""Tests de import de producto Dropi → WooCommerce (feature 014)."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from app.services.admin import scout_import


def _detail(pid=2175936):
    return {
        "id": pid,
        "name": "Juguete para gato raton a control",
        "sku": "LCT0001",
        "type": "SIMPLE",
        "description": "<p>Juguete</p>",
        "sale_price": 6500,
        "suggested_price": 18500,
        "user_id": 465197,
        "user": {"id": 465197, "name": "Andres"},
        "categories": [{"name": "Mascotas"}],
        "variations": [],
        "warehouse_product": [{"stock": 150}],
        "photos": [{"url": None, "urlS3": "colombia/products/2175936/foto uno.png"}],
    }


@pytest.mark.asyncio
async def test_import_creates_product_with_dropi_meta():
    wc = AsyncMock()
    wc.find_product_by_sku = AsyncMock(return_value=None)
    wc.create_product = AsyncMock(
        return_value={
            "id": 555,
            "name": "Juguete para gato raton a control",
            "permalink": "https://t/p/555",
        }
    )
    with (
        patch.object(
            scout_import.dropi, "get_product_detail", new=AsyncMock(return_value=_detail())
        ),
        patch.object(scout_import, "get_wc_client", new=AsyncMock(return_value=wc)),
        patch.object(scout_import.settings, "DROPI_INTEGRATION_KEY", "tok-xyz"),
    ):
        res = await scout_import.import_product(2175936)

    assert res == {
        "status": "created",
        "wc_id": 555,
        "name": "Juguete para gato raton a control",
        "permalink": "https://t/p/555",
    }
    payload = wc.create_product.call_args.args[0]
    assert payload["sku"] == "LCT0001"
    assert payload["regular_price"] == "18500"  # precio sugerido
    assert payload["status"] == "draft"
    assert payload["stock_quantity"] == 150
    # imagen con urlS3 → URL absoluta, espacios codificados
    assert payload["images"][0]["src"].endswith("foto%20uno.png")
    # meta que el plugin Dropi necesita para sincronizar órdenes
    meta = {m["key"]: m["value"] for m in payload["meta_data"]}
    assert meta["_dropi_product_id"] == "2175936"
    assert meta["_dropi_token"] == "tok-xyz"
    dp = json.loads(meta["_dropi_product"])
    assert dp["id"] == 2175936 and dp["user_id"] == 465197 and dp["sku"] == "LCT0001"


@pytest.mark.asyncio
async def test_import_idempotent_when_sku_exists():
    wc = AsyncMock()
    wc.find_product_by_sku = AsyncMock(
        return_value={"id": 99, "name": "ya existe", "permalink": "https://t/p/99"}
    )
    wc.create_product = AsyncMock()
    with (
        patch.object(
            scout_import.dropi, "get_product_detail", new=AsyncMock(return_value=_detail())
        ),
        patch.object(scout_import, "get_wc_client", new=AsyncMock(return_value=wc)),
        patch.object(scout_import.settings, "DROPI_INTEGRATION_KEY", "tok"),
    ):
        res = await scout_import.import_product(2175936)

    assert res["status"] == "exists" and res["wc_id"] == 99
    wc.create_product.assert_not_called()  # no duplica


@pytest.mark.asyncio
async def test_import_requires_token():
    with patch.object(scout_import.settings, "DROPI_INTEGRATION_KEY", ""):
        with pytest.raises(RuntimeError):
            await scout_import.import_product(1)


def test_image_urls_builds_absolute_encoded():
    urls = scout_import.dropi.image_urls(_detail())
    assert urls == ["https://api.dropi.co/colombia/products/2175936/foto%20uno.png"]


@pytest.mark.asyncio
async def test_wc_create_and_find_by_sku():
    """Cobertura de _post/create_product/find_product_by_sku con respx."""
    import httpx
    import respx
    from app.clients.woocommerce import WooCommerceClient
    from app.config import settings

    async with WooCommerceClient() as wc:
        with respx.mock:
            respx.post(f"{settings.WC_BASE_URL}/products").mock(
                return_value=httpx.Response(201, json={"id": 7, "name": "X"})
            )
            created = await wc.create_product({"name": "X"})
            assert created["id"] == 7

            respx.get(f"{settings.WC_BASE_URL}/products").mock(
                return_value=httpx.Response(200, json=[{"id": 7, "sku": "S1"}])
            )
            found = await wc.find_product_by_sku("S1")
            assert found["id"] == 7
            assert await wc.find_product_by_sku("") is None


@pytest.mark.asyncio
async def test_wc_create_propagates_errors():
    import httpx
    import respx
    from app.clients.woocommerce import WCClientError, WCServerError, WooCommerceClient
    from app.config import settings

    async with WooCommerceClient() as wc:
        with respx.mock:
            respx.post(f"{settings.WC_BASE_URL}/products").mock(
                return_value=httpx.Response(400, text="bad")
            )
            with pytest.raises(WCClientError):
                await wc.create_product({})
        with respx.mock:
            respx.post(f"{settings.WC_BASE_URL}/products").mock(
                return_value=httpx.Response(500, text="boom")
            )
            with pytest.raises(WCServerError):
                await wc.create_product({})


@pytest.mark.asyncio
async def test_import_endpoint_201_and_409_paths(admin_client):
    """POST /scout/import: 201 created y 400/502 mapeados."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "app.services.admin.scout_import.import_product",
        new=AsyncMock(
            return_value={"status": "created", "wc_id": 1, "name": "X", "permalink": "p"}
        ),
    ):
        r = await admin_client.post("/v1/admin/scout/import/123")
        assert r.status_code == 201 and r.json()["wc_id"] == 1

    with patch(
        "app.services.admin.scout_import.import_product",
        new=AsyncMock(side_effect=RuntimeError("DROPI_INTEGRATION_KEY no configurado")),
    ):
        r = await admin_client.post("/v1/admin/scout/import/123")
        assert r.status_code == 400
