"""Fixtures compartidas de los tests del panel admin (feature 012)."""

from unittest.mock import AsyncMock, patch

import pytest
from app.core.admin_auth import require_admin_session
from app.main import app
from httpx import ASGITransport, AsyncClient

ADMIN_AUTH = {"Authorization": "Bearer admin-test-token"}


@pytest.fixture
async def admin_client():
    """Cliente con la sesión admin ya resuelta (override del dependency)."""
    app.dependency_overrides[require_admin_session] = lambda: "admin-test-token"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(require_admin_session, None)


@pytest.fixture
def no_cache():
    """Cache Redis transparente (miss siempre, set/delete no-op)."""
    with (
        patch("app.core.cache.cache_get", new_callable=AsyncMock, return_value=None),
        patch("app.core.cache.cache_set", new_callable=AsyncMock),
        patch("app.core.cache.cache_delete", new_callable=AsyncMock),
        patch("app.services.admin.stats.cache_get", new_callable=AsyncMock, return_value=None),
        patch("app.services.admin.stats.cache_set", new_callable=AsyncMock),
        patch("app.services.admin.customers.cache_get", new_callable=AsyncMock, return_value=None),
        patch("app.services.admin.customers.cache_set", new_callable=AsyncMock),
        patch(
            "app.services.admin.products_admin.cache_get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.admin.products_admin.cache_set", new_callable=AsyncMock),
        patch("app.services.admin.products_admin.cache_delete", new_callable=AsyncMock),
    ):
        yield


def make_order(
    oid=1,
    status="processing",
    total="49900",
    phone="3001234567",
    name=("Maria", "Paula"),
    city="Cali",
    payment="cod",
    items=None,
    metas=None,
    date="2026-06-12T10:00:00",
):
    return {
        "id": oid,
        "number": str(oid),
        "date_created": date,
        "status": status,
        "total": total,
        "payment_method": payment,
        "payment_method_title": "Pago contraentrega" if payment == "cod" else payment,
        "billing": {
            "first_name": name[0],
            "last_name": name[1],
            "phone": phone,
            "city": city,
            "state": "VAC",
            "address_1": "Calle 1",
            "address_2": "",
        },
        "line_items": items
        or [
            {
                "product_id": 84,
                "name": "Mini Licuadora",
                "quantity": 1,
                "price": 49900,
                "total": total,
            }
        ],
        "meta_data": [{"key": k, "value": v} for k, v in (metas or {}).items()],
    }


DROPI_META_SERIALIZED = (
    'O:8:"stdClass":18:{s:2:"id";i:99;s:10:"sale_price";s:8:"28000.00";'
    's:15:"suggested_price";s:8:"35000.00";}'
)


def make_product(pid=84, price="49900", dropi=True, stock=100):
    metas = []
    if dropi:
        metas = [
            {"key": "_dropi_product_id", "value": "99"},
            {"key": "_dropi_product", "value": DROPI_META_SERIALIZED},
            {"key": "_dropi_token", "value": "SECRET-JWT-NO-EXPONER"},
        ]
    return {
        "id": pid,
        "name": f"Producto {pid}",
        "price": price,
        "regular_price": price,
        "stock_quantity": stock,
        "stock_status": "instock",
        "status": "publish",
        "images": [{"src": "https://img/x.jpg"}],
        "meta_data": metas,
    }
