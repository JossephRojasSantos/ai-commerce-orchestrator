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
        "dropi": {"isSuccess": True, "objects": {"id": 555}},
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


def test_to_dto_maps_landing_content():
    """Reviews/faq/escasez reales viven en content.landing (feature 019)."""
    from types import SimpleNamespace

    from app.services.store import _to_dto

    p = SimpleNamespace(
        slug="delantal",
        name="Delantal",
        price=29900,
        anchor_price=None,
        description="d",
        short_description="c",
        dropi_product_id=None,
        dropi_supplier_id=None,
        images=["https://x/img.jpg"],
        content={
            "reviews": "210",  # contador, NO las reseñas
            "rating": "4.8",
            "landing": {
                "reviews": [{"name": "Maria", "city": "Cali", "stars": 5, "text": "Excelente"}],
                "faq": [{"q": "¿Cómo pago?", "a": "Contraentrega"}],
                "scarcity_units": 7,
                "price_old": 49900,
                "compare": [],
            },
        },
    )
    dto = _to_dto(p)  # type: ignore[arg-type]
    assert dto["resenas"] == [
        {"autor": "Maria — Cali", "estrellas": 5, "texto": "Excelente", "foto": None}
    ]
    assert dto["faq"] == [{"pregunta": "¿Cómo pago?", "respuesta": "Contraentrega"}]
    assert dto["escasez"] == {"activa": True, "mensaje": "¡Quedan solo 7 unidades!"}
    assert dto["precioAncla"] == 49900.0
    assert dto["comparativa"] is None


def test_to_dto_tolerates_malformed_content():
    """Strings donde se esperan listas no deben tumbar el catálogo."""
    from types import SimpleNamespace

    from app.services.store import _to_dto

    p = SimpleNamespace(
        slug="x",
        name="X",
        price=1000,
        anchor_price=None,
        description="",
        short_description="",
        dropi_product_id=None,
        dropi_supplier_id=None,
        images=None,
        content={"reviews": "210", "landing": "no-es-dict"},
    )
    dto = _to_dto(p)  # type: ignore[arg-type]
    assert dto["resenas"] == []
    assert dto["faq"] == []
    assert dto["galeria"] == []
    assert dto["escasez"] is None
