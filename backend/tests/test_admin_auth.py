"""Tests de autenticación del panel admin (T006)."""

from unittest.mock import AsyncMock, patch

import pytest
from app.core import admin_auth
from app.main import app
from httpx import ASGITransport, AsyncClient

_SALT = "testsalt"
_PASSWORD = "super-secreta-123"
_HASH = admin_auth.hash_password(_PASSWORD, _SALT)


def _patch_settings():
    return patch.multiple(
        "app.core.admin_auth.settings",
        ADMIN_PASSWORD_HASH=_HASH,
        ADMIN_PASSWORD_SALT=_SALT,
    )


async def _post_login(password, blocked=False):
    with (
        _patch_settings(),
        patch(
            "app.routers.admin.check_login_blocked",
            new_callable=AsyncMock,
            return_value=blocked,
        ),
        patch("app.routers.admin.register_login_failure", new_callable=AsyncMock) as mock_fail,
        patch(
            "app.routers.admin.create_session",
            new_callable=AsyncMock,
            return_value="tok123",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/admin/login", json={"password": password})
    return resp, mock_fail


def test_hash_roundtrip():
    with _patch_settings():
        assert admin_auth.verify_password(_PASSWORD) is True
        assert admin_auth.verify_password("otra") is False


def test_verify_rejects_when_unconfigured():
    with patch.multiple(
        "app.core.admin_auth.settings", ADMIN_PASSWORD_HASH="", ADMIN_PASSWORD_SALT=""
    ):
        assert admin_auth.verify_password("cualquiera") is False


@pytest.mark.asyncio
async def test_login_ok():
    resp, _ = await _post_login(_PASSWORD)
    assert resp.status_code == 200
    assert resp.json()["token"] == "tok123"


@pytest.mark.asyncio
async def test_login_wrong_password_registers_failure():
    resp, mock_fail = await _post_login("incorrecta")
    assert resp.status_code == 401
    mock_fail.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_blocked_ip():
    resp, _ = await _post_login(_PASSWORD, blocked=True)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_protected_endpoint_requires_session():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/admin/stats")
    assert resp.status_code in (401, 422)
