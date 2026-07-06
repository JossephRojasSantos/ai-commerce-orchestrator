"""Tests de la API tienda headless /v1/store (fase 2 migración WP)."""

from unittest.mock import AsyncMock, patch

import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient

SECRET = "store-test-secret"
AUTH = {"X-Store-Secret": SECRET}

PRODUCT_DTO = {
    "slug": "afilador-cuchillos",
    "nombre": "Afilador De Cuchillos",
    "precioVenta": 35000.0,
    "precioAncla": 49900.0,
    "dropiId": 96,
    "supplierId": 923,
    "descripcion": "desc",
    "descripcionCorta": "corta",
    "galeria": ["https://cdn/img1.jpg"],
    "resenas": [{"autor": "Maria", "estrellas": 5, "texto": "ok"}],
    "faq": [],
    "comparativa": None,
    "escasez": None,
    "contenido": {},
}


@pytest.fixture
async def store_client(monkeypatch):
    monkeypatch.setattr(settings, "STORE_API_SECRET", SECRET)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_products_requires_secret(store_client):
    resp = await store_client.get("/v1/store/products")
    assert resp.status_code == 401
    resp = await store_client.get("/v1/store/products", headers={"X-Store-Secret": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_secret_empty_always_denies(store_client, monkeypatch):
    """Sin STORE_API_SECRET configurado, la API queda cerrada (no abierta)."""
    monkeypatch.setattr(settings, "STORE_API_SECRET", "")
    resp = await store_client.get("/v1/store/products", headers={"X-Store-Secret": ""})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_products(store_client):
    with patch(
        "app.routers.store.store.list_products", new_callable=AsyncMock, return_value=[PRODUCT_DTO]
    ):
        resp = await store_client.get("/v1/store/products", headers=AUTH)
    assert resp.status_code == 200
    items = resp.json()
    assert items[0]["slug"] == "afilador-cuchillos"
    assert items[0]["precioVenta"] == 35000.0


@pytest.mark.asyncio
async def test_product_by_slug_404(store_client):
    with patch("app.routers.store.store.get_product", new_callable=AsyncMock, return_value=None):
        resp = await store_client.get("/v1/store/products/no-existe", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_order_copy_created(store_client):
    body = {
        "shopOrderId": "TM-123-abc",
        "total": 35000,
        "cliente": {"nombre": "Test", "telefono": "3166235026"},
        "productos": [{"id": 96, "quantity": 1, "price": 35000, "user_id": 923}],
        "dropi": {"isSuccess": True, "order": {"id": 555}},
    }
    with patch(
        "app.routers.store.store.save_order", new_callable=AsyncMock, return_value=1
    ) as mock_save:
        resp = await store_client.post("/v1/store/orders", headers=AUTH, json=body)
    assert resp.status_code == 201
    assert resp.json() == {"id": 1, "shopOrderId": "TM-123-abc"}
    mock_save.assert_awaited_once()


@pytest.mark.asyncio
async def test_order_copy_validation(store_client):
    resp = await store_client.post(
        "/v1/store/orders", headers=AUTH, json={"shopOrderId": "", "total": 0}
    )
    assert resp.status_code == 422
