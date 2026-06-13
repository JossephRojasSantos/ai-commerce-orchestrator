"""Tests de la ingesta Dropi: paginación, dedup, runs, lock (T007)."""

from unittest.mock import patch

import httpx
import pytest
import respx
from app.clients import dropi
from app.config import settings


def _page(products):
    return httpx.Response(200, json={"isSuccess": True, "objects": products})


def _product(pid, stock=100):
    return {
        "id": pid,
        "name": f"Producto {pid}",
        "sale_price": 10000,
        "suggested_price": 30000,
        "description": "desc",
        "categories": [{"name": "Hogar"}],
        "user": {"name": "Prov", "plan": {"name": "BASIC"}},
        "warehouse_product": [{"stock": stock}],
    }


@pytest.mark.asyncio
@respx.mock
async def test_list_products_sends_waf_headers_and_filters():
    route = respx.post(f"{settings.DROPI_API_BASE}/products/index").mock(
        return_value=_page([_product(1)])
    )
    with patch.object(settings, "DROPI_INTEGRATION_KEY", "tok-test"):
        out = await dropi.list_products(0)
    assert len(out) == 1
    req = route.calls[0].request
    assert req.headers["user-agent"] == settings.DROPI_USER_AGENT  # WAF (research R1)
    assert req.headers["dropi-integration-key"] == "tok-test"
    import json

    body = json.loads(req.content)
    assert body["stockmayor"] == 1 and body["userVerified"] is True
    assert body["get_stock"] is False and body["active"] is True


@pytest.mark.asyncio
@respx.mock
async def test_list_products_error_raises():
    respx.post(f"{settings.DROPI_API_BASE}/products/index").mock(
        return_value=httpx.Response(200, json={"isSuccess": False, "status": 401})
    )
    with pytest.raises(RuntimeError):
        await dropi.list_products(0)


def test_stock_total_aggregates_warehouses():
    p = {"warehouse_product": [{"stock": 100}, {"stock": 50}, {"stock": None}]}
    assert dropi.stock_total(p) == 150
    assert dropi.stock_total({}) == 0


def test_first_category():
    assert dropi.first_category(_product(1)) == "Hogar"
    assert dropi.first_category({"categories": []}) is None


@pytest.mark.asyncio
async def test_ingest_skipped_without_token():
    from app.workers.scout_ingest import run_ingest

    with patch.object(settings, "DROPI_INTEGRATION_KEY", ""):
        result = await run_ingest()
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_ingest_lock_blocks_concurrent():
    """Segundo run con lock activo devuelve None (FR-016)."""
    from app.workers import scout_ingest

    class FakeRedis:
        async def set(self, *a, **kw):
            return None  # lock ya tomado

        async def delete(self, *a):
            pass

        async def aclose(self):
            pass

    with patch("redis.asyncio.from_url", return_value=FakeRedis()):
        result = await scout_ingest.run_ingest_locked()
    assert result is None


@pytest.mark.asyncio
async def test_ingest_lock_released_after_run():
    from app.workers import scout_ingest

    calls = {"set": 0, "delete": 0}

    class FakeRedis:
        async def set(self, *a, **kw):
            calls["set"] += 1
            return True

        async def delete(self, *a):
            calls["delete"] += 1

        async def aclose(self):
            pass

    with (
        patch("redis.asyncio.from_url", return_value=FakeRedis()),
        patch.object(scout_ingest, "run_ingest", return_value={"status": "ok"}),
    ):
        result = await scout_ingest.run_ingest_locked()
    assert result == {"status": "ok"}
    assert calls == {"set": 1, "delete": 1}  # lock liberado


@pytest.mark.asyncio
@respx.mock
async def test_list_categories():
    respx.get(f"{settings.DROPI_API_BASE}/categories/").mock(
        return_value=httpx.Response(
            200, json={"isSuccess": True, "objects": [{"id": 1, "name": "Hogar"}]}
        )
    )
    out = await dropi.list_categories()
    assert out == [{"id": 1, "name": "Hogar"}]


@pytest.mark.asyncio
@respx.mock
async def test_list_categories_failure_raises():
    respx.get(f"{settings.DROPI_API_BASE}/categories/").mock(
        return_value=httpx.Response(200, json={"isSuccess": False})
    )
    with pytest.raises(RuntimeError):
        await dropi.list_categories()
