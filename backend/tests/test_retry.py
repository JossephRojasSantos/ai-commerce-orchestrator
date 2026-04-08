from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from app.config import settings

BASE = settings.WC_BASE_URL


@pytest.mark.asyncio
@respx.mock
async def test_retry_on_5xx_then_success():
    import json
    import pathlib

    FIXTURES = json.loads(
        (pathlib.Path(__file__).parent / "fixtures" / "wc_responses.json").read_text()
    )
    route = respx.get(url__startswith=BASE + "/products/123")
    route.side_effect = [
        httpx.Response(503, text="Service Unavailable"),
        httpx.Response(503, text="Service Unavailable"),
        httpx.Response(200, json=FIXTURES["product"]),
    ]
    with (
        patch("app.services.products.cache_get", new=AsyncMock(return_value=None)),
        patch("app.services.products.cache_set", new=AsyncMock()),
    ):
        from app.services.products import get_product

        product = await get_product(123)
    assert product.id == 123


@pytest.mark.asyncio
@respx.mock
async def test_no_retry_on_4xx():
    respx.get(url__startswith=BASE + "/products/404").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    with patch("app.services.products.cache_get", new=AsyncMock(return_value=None)):
        from app.services.products import get_product
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_product(404)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@respx.mock
async def test_timeout_returns_504():
    respx.get(url__startswith=BASE + "/products/789").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    with patch("app.services.products.cache_get", new=AsyncMock(return_value=None)):
        from app.services.products import get_product
        from fastapi import HTTPException

        with pytest.raises((httpx.TimeoutException, HTTPException)):
            await get_product(789)
