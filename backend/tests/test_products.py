import json
import pathlib
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import httpx
import pytest
import respx
from app.config import settings

FIXTURES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "wc_responses.json").read_text()
)

BASE = settings.WC_BASE_URL


@pytest.mark.asyncio
@respx.mock
async def test_list_products_ok():
    respx.get(url__startswith=BASE + "/products").mock(
        return_value=httpx.Response(200, json=FIXTURES["product_list"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.products import list_products

        products = await list_products()
    assert len(products) == 1
    assert products[0].id == 123


@pytest.mark.asyncio
@respx.mock
async def test_get_product_ok():
    respx.get(url__startswith=BASE + "/products/123").mock(
        return_value=httpx.Response(200, json=FIXTURES["product"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.products import get_product

        product = await get_product(123)
    assert product.id == 123
    assert product.name == "Producto Test"


@pytest.mark.asyncio
@respx.mock
async def test_get_product_404():
    respx.get(url__startswith=BASE + "/products/999").mock(
        return_value=httpx.Response(404, json=FIXTURES["error_404"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.products import get_product
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_product(999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_products_uses_cache():
    """Test que cache hit no llama a WC API"""
    cached = FIXTURES["product_list"]
    fake_redis = fakeredis.aioredis.FakeRedis()
    with (
        patch("app.core.cache.get_redis", return_value=fake_redis),
        patch("app.services.products.cache_get", new=AsyncMock(return_value=cached)),
    ):
        from app.services.products import list_products

        products = await list_products()
    assert products[0].id == 123


@pytest.mark.asyncio
@respx.mock
async def test_get_product_500_server_error():
    respx.get(url__startswith=BASE + "/products/789").mock(
        return_value=httpx.Response(500, json=FIXTURES["error_500"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.products import get_product
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_product(789)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@respx.mock
async def test_list_products_500_server_error():
    respx.get(url__startswith=BASE + "/products").mock(
        return_value=httpx.Response(500, json=FIXTURES["error_500"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.products import list_products
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await list_products()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@respx.mock
async def test_get_product_401_client_error():
    respx.get(url__startswith=BASE + "/products/555").mock(
        return_value=httpx.Response(401, json={"code": "auth_error"})
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.products import get_product
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_product(555)
    assert exc.value.status_code == 401
