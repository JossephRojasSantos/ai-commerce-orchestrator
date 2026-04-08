import json
import pathlib
from unittest.mock import patch

import fakeredis.aioredis
import httpx
import pytest
import respx
from app.config import settings
from fastapi import HTTPException

FIXTURES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "wc_responses.json").read_text()
)

BASE = settings.WC_BASE_URL


@pytest.mark.asyncio
@respx.mock
async def test_get_order_ok():
    respx.get(url__startswith=BASE + "/orders/456").mock(
        return_value=httpx.Response(200, json=FIXTURES["order"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.orders import get_order

        order = await get_order(456)
    assert order.id == 456
    assert order.status == "processing"


@pytest.mark.asyncio
@respx.mock
async def test_list_orders_by_customer_ok():
    respx.get(url__startswith=BASE + "/orders").mock(
        return_value=httpx.Response(200, json=FIXTURES["order_list"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.orders import list_orders_by_customer

        orders = await list_orders_by_customer(42)
    assert len(orders) == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_order_not_found():
    respx.get(url__startswith=BASE + "/orders/999").mock(
        return_value=httpx.Response(404, json=FIXTURES["error_404"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.orders import get_order

        with pytest.raises(HTTPException) as exc:
            await get_order(999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@respx.mock
async def test_get_order_500_server_error():
    respx.get(url__startswith=BASE + "/orders/999").mock(
        return_value=httpx.Response(500, json=FIXTURES["error_500"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.orders import get_order

        with pytest.raises(HTTPException) as exc:
            await get_order(999)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@respx.mock
async def test_list_orders_by_customer_500_server_error():
    respx.get(url__startswith=BASE + "/orders").mock(
        return_value=httpx.Response(500, json=FIXTURES["error_500"])
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.orders import list_orders_by_customer

        with pytest.raises(HTTPException) as exc:
            await list_orders_by_customer(999)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@respx.mock
async def test_get_order_401_auth_error():
    respx.get(url__startswith=BASE + "/orders/888").mock(
        return_value=httpx.Response(401, json={"code": "auth_error"})
    )
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.core.cache.get_redis", return_value=fake_redis):
        from app.services.orders import get_order

        with pytest.raises(HTTPException) as exc:
            await get_order(888)
    assert exc.value.status_code == 401
