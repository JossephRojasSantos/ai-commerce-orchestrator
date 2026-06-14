"""Tests del editor de productos: detalle, visibilidad, descripción, imágenes (feature 015)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.admin.conftest import ADMIN_AUTH, make_product


@pytest.mark.asyncio
async def test_product_detail_includes_description_images_visible(admin_client, no_cache):
    p = make_product(99, price="490000", dropi=True)
    p["description"] = "<p>Cepillo</p>"
    p["short_description"] = "corto"
    p["images"] = [{"id": 5, "src": "https://img/a.jpg"}]
    p["permalink"] = "https://t/p/99"
    wc = MagicMock()
    wc.get_product_raw = AsyncMock(return_value=p)
    with patch(
        "app.services.admin.products_admin.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.get("/v1/admin/products/99", headers=ADMIN_AUTH)
    d = resp.json()
    assert d["description"] == "<p>Cepillo</p>"
    assert d["images"] == [{"id": 5, "src": "https://img/a.jpg"}]
    assert d["visible"] is True
    assert "meta_data" not in resp.text  # token Dropi nunca sale


@pytest.mark.asyncio
async def test_product_detail_includes_landing_config(admin_client, no_cache):
    import json

    p = make_product(99, price="490000")
    p.setdefault("meta_data", []).append(
        {
            "key": "_tm_landing",
            "value": json.dumps({"sections": {"faq": False}, "subtitle": "Gancho"}),
        }
    )
    wc = MagicMock()
    wc.get_product_raw = AsyncMock(return_value=p)
    with patch(
        "app.services.admin.products_admin.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.get("/v1/admin/products/99", headers=ADMIN_AUTH)
    d = resp.json()
    assert d["landing"]["subtitle"] == "Gancho"
    assert d["landing"]["sections"]["faq"] is False


@pytest.mark.asyncio
async def test_update_landing_writes_meta(admin_client, no_cache):
    import json

    captured = {}

    async def fake_update(pid, payload):
        captured.update(payload)
        return make_product(99)

    wc = MagicMock()
    wc.update_product = AsyncMock(side_effect=fake_update)
    landing = {
        "sections": {"hero": True},
        "benefits": [{"icon": "🔋", "title": "USB", "text": "x"}],
    }
    with patch(
        "app.services.admin.products_admin.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.put(
            "/v1/admin/products/99", headers=ADMIN_AUTH, json={"landing": landing}
        )
    assert resp.status_code == 200
    meta = {m["key"]: m["value"] for m in captured["meta_data"]}
    assert json.loads(meta["_tm_landing"])["benefits"][0]["title"] == "USB"


@pytest.mark.asyncio
async def test_update_visible_toggles_status(admin_client, no_cache):
    captured = {}

    async def fake_update(pid, payload):
        captured.update(payload)
        return {**make_product(99), "status": "draft"}

    wc = MagicMock()
    wc.update_product = AsyncMock(side_effect=fake_update)
    with patch(
        "app.services.admin.products_admin.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.put(
            "/v1/admin/products/99", json={"visible": False}, headers=ADMIN_AUTH
        )
    assert resp.status_code == 200
    assert captured["status"] == "draft" and captured["catalog_visibility"] == "hidden"
    assert resp.json()["visible"] is False


@pytest.mark.asyncio
async def test_update_name_and_description(admin_client, no_cache):
    captured = {}

    async def fake_update(pid, payload):
        captured.update(payload)
        return make_product(99)

    wc = MagicMock()
    wc.update_product = AsyncMock(side_effect=fake_update)
    with patch(
        "app.services.admin.products_admin.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.put(
            "/v1/admin/products/99",
            json={"name": "Nuevo", "description": "<p>desc</p>"},
            headers=ADMIN_AUTH,
        )
    assert resp.status_code == 200
    assert captured["name"] == "Nuevo" and captured["description"] == "<p>desc</p>"


@pytest.mark.asyncio
async def test_update_nothing_returns_422(admin_client, no_cache):
    resp = await admin_client.put("/v1/admin/products/99", json={}, headers=ADMIN_AUTH)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_image_appends_and_keeps_existing(admin_client, no_cache):
    captured = {}

    async def fake_update(pid, payload):
        captured.update(payload)
        return make_product(99)

    wc = MagicMock()
    wc.get_product_raw = AsyncMock(return_value={"images": [{"id": 5}, {"id": 6}]})
    wc.update_product = AsyncMock(side_effect=fake_update)
    with (
        patch(
            "app.services.admin.products_admin.get_wc_client",
            new_callable=AsyncMock,
            return_value=wc,
        ),
        patch(
            "app.services.admin.media_store.store_image",
            new=AsyncMock(return_value="abc123"),
        ),
        patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "PUBLIC_API_BASE",
            "https://api.test",
        ),
    ):
        resp = await admin_client.post(
            "/v1/admin/products/99/image",
            files={"file": ("c.png", b"\x89PNGfake", "image/png")},
            headers=ADMIN_AUTH,
        )
    assert resp.status_code == 201
    # conserva las 2 existentes por id + agrega la nueva por src
    assert {"id": 5} in captured["images"] and {"id": 6} in captured["images"]
    assert captured["images"][-1]["src"] == "https://api.test/v1/public/media/abc123"


@pytest.mark.asyncio
async def test_upload_image_rejects_bad_mime(admin_client, no_cache):
    resp = await admin_client.post(
        "/v1/admin/products/99/image",
        files={"file": ("x.pdf", b"%PDF", "application/pdf")},
        headers=ADMIN_AUTH,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_image_keeps_others(admin_client, no_cache):
    captured = {}

    async def fake_update(pid, payload):
        captured.update(payload)
        return make_product(99)

    wc = MagicMock()
    wc.get_product_raw = AsyncMock(return_value={"images": [{"id": 5}, {"id": 6}]})
    wc.update_product = AsyncMock(side_effect=fake_update)
    with patch(
        "app.services.admin.products_admin.get_wc_client", new_callable=AsyncMock, return_value=wc
    ):
        resp = await admin_client.delete("/v1/admin/products/99/image/5", headers=ADMIN_AUTH)
    assert resp.status_code == 200
    assert captured["images"] == [{"id": 6}]  # quitó la 5


@pytest.mark.asyncio
async def test_public_media_serves_stored_bytes(admin_client):
    from app.services.admin import media_store

    with patch.object(
        media_store, "get_image", new=AsyncMock(return_value=(b"PNGDATA", "image/png"))
    ):
        resp = await admin_client.get("/v1/public/media/xyz")
    assert resp.status_code == 200
    assert resp.content == b"PNGDATA"
    assert resp.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_public_media_404_when_missing(admin_client):
    from app.services.admin import media_store

    with patch.object(media_store, "get_image", new=AsyncMock(return_value=None)):
        resp = await admin_client.get("/v1/public/media/nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_config_exposes_clarity_id(admin_client):
    from app.config import settings

    with patch.object(settings, "CLARITY_PROJECT_ID", "abc123"):
        resp = await admin_client.get("/v1/admin/config", headers=ADMIN_AUTH)
    assert resp.status_code == 200
    assert resp.json()["clarity_project_id"] == "abc123"


@pytest.mark.asyncio
async def test_media_store_roundtrip():
    """store_image → get_image devuelve los mismos bytes y mime (Redis fake)."""
    from app.services.admin import media_store

    store = {}

    class FakeRedis:
        async def set(self, k, v, ex=None):
            store[k] = v

        async def get(self, k):
            return store.get(k)

        async def aclose(self):
            pass

    with patch.object(media_store, "_redis", return_value=FakeRedis()):
        mid = await media_store.store_image(b"\x89PNG-bytes", "image/png")
        got = await media_store.get_image(mid)
    assert got == (b"\x89PNG-bytes", "image/png")
    assert media_store.public_url(mid).endswith(f"/v1/public/media/{mid}")


@pytest.mark.asyncio
async def test_media_store_missing_returns_none():
    from app.services.admin import media_store

    class FakeRedis:
        async def get(self, k):
            return None

        async def aclose(self):
            pass

    with patch.object(media_store, "_redis", return_value=FakeRedis()):
        assert await media_store.get_image("nope") is None


@pytest.mark.asyncio
async def test_media_id_has_extension_for_wp():
    """El id debe terminar en extensión de imagen (WP la exige al hacer sideload)."""
    from app.services.admin import media_store

    store = {}

    class FakeRedis:
        async def set(self, k, v, ex=None):
            store[k] = v

        async def get(self, k):
            return store.get(k)

        async def aclose(self):
            pass

    with patch.object(media_store, "_redis", return_value=FakeRedis()):
        mid = await media_store.store_image(b"x", "image/jpeg")
        assert mid.endswith(".jpg")
        mid2 = await media_store.store_image(b"x", "image/webp")
        assert mid2.endswith(".webp")
