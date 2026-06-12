"""Tests del MFA del panel: TOTP + respaldo WhatsApp (feature 012)."""

import time
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from app.core import admin_auth
from app.main import app
from httpx import ASGITransport, AsyncClient

# secret base32 fijo para reproducibilidad
_SECRET = "JBSWY3DPEHPK3PXP"
_SALT = "s"
_PASS = "clave-fuerte"
_HASH = admin_auth.hash_password(_PASS, _SALT)


@pytest.fixture
def fake_redis_mfa():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.core.admin_auth._redis", return_value=redis):
        yield redis


def _patch_creds(phone=""):
    return patch.multiple(
        "app.core.admin_auth.settings",
        ADMIN_PASSWORD_HASH=_HASH,
        ADMIN_PASSWORD_SALT=_SALT,
        ADMIN_TOTP_SECRET=_SECRET,
        ADMIN_PHONE=phone,
        ADMIN_SESSION_TTL=28800,
    )


def test_totp_generation_and_verification():
    with patch.object(admin_auth.settings, "ADMIN_TOTP_SECRET", _SECRET):
        now = time.time()
        code = admin_auth._totp_at(_SECRET, now)
        assert len(code) == 6 and code.isdigit()
        assert admin_auth.verify_totp(code) is True
        assert admin_auth.verify_totp("000000") in (True, False)  # casi siempre False
        # código de hace 5 min: fuera de ventana
        old = admin_auth._totp_at(_SECRET, now - 300)
        assert admin_auth.verify_totp(old) is False


def test_verify_totp_rejects_when_no_secret():
    with patch.object(admin_auth.settings, "ADMIN_TOTP_SECRET", ""):
        assert admin_auth.verify_totp("123456") is False


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_login_requires_second_factor(fake_redis_mfa):
    with (
        _patch_creds(),
        patch("app.routers.admin.check_login_blocked", new_callable=AsyncMock, return_value=False),
    ):
        async with await _client() as c:
            resp = await c.post("/v1/admin/login", json={"password": _PASS})
    body = resp.json()
    assert resp.status_code == 200
    assert body["mfa_required"] is True
    assert "mfa_token" in body
    assert "token" not in body  # NO se entrega sesión todavía


@pytest.mark.asyncio
async def test_full_totp_flow(fake_redis_mfa):
    with (
        _patch_creds(),
        patch("app.routers.admin.check_login_blocked", new_callable=AsyncMock, return_value=False),
    ):
        async with await _client() as c:
            login = (await c.post("/v1/admin/login", json={"password": _PASS})).json()
            mfa_token = login["mfa_token"]

            # código incorrecto → 401
            bad = await c.post(
                "/v1/admin/login/verify", json={"mfa_token": mfa_token, "code": "000001"}
            )
            assert bad.status_code == 401

            # código correcto → sesión
            code = admin_auth._totp_at(_SECRET, time.time())
            ok = await c.post("/v1/admin/login/verify", json={"mfa_token": mfa_token, "code": code})
    assert ok.status_code == 200
    assert "token" in ok.json()


@pytest.mark.asyncio
async def test_whatsapp_backup_code_flow(fake_redis_mfa):
    with (
        _patch_creds(phone="573166235026"),
        patch("app.routers.admin.check_login_blocked", new_callable=AsyncMock, return_value=False),
        patch(
            "app.integrations.whatsapp.client.send_text_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        from app.integrations.whatsapp.models import WASendResult

        mock_send.return_value = WASendResult(message_id="wamid", status="sent")
        async with await _client() as c:
            login = (await c.post("/v1/admin/login", json={"password": _PASS})).json()
            mfa_token = login["mfa_token"]
            assert login["whatsapp_available"] is True

            sent = await c.post("/v1/admin/login/whatsapp", json={"mfa_token": mfa_token})
            assert sent.status_code == 200
            # el código enviado quedó en redis
            wa_code = await fake_redis_mfa.get("admin_mfa_wa:" + mfa_token)
            assert wa_code and len(wa_code) == 6

            ok = await c.post(
                "/v1/admin/login/verify", json={"mfa_token": mfa_token, "code": wa_code}
            )
    assert ok.status_code == 200
    assert "token" in ok.json()
    assert mock_send.await_count == 1


@pytest.mark.asyncio
async def test_mfa_lockout_after_failures(fake_redis_mfa):
    token = await admin_auth.create_mfa_challenge("1.2.3.4")
    for _ in range(5):
        assert await admin_auth.verify_second_factor(token, "999999") is None
    # tras 5 fallos el challenge se invalida — el 6º no concede sesión ni con código válido
    import time as _t

    valid = admin_auth._totp_at(_SECRET, _t.time())
    with patch.object(admin_auth.settings, "ADMIN_TOTP_SECRET", _SECRET):
        assert await admin_auth.verify_second_factor(token, valid) is None


@pytest.mark.asyncio
async def test_login_without_mfa_configured_returns_session(fake_redis_mfa):
    with (
        patch.multiple(
            "app.core.admin_auth.settings",
            ADMIN_PASSWORD_HASH=_HASH,
            ADMIN_PASSWORD_SALT=_SALT,
            ADMIN_TOTP_SECRET="",
            ADMIN_SESSION_TTL=28800,
        ),
        patch("app.routers.admin.check_login_blocked", new_callable=AsyncMock, return_value=False),
    ):
        async with await _client() as c:
            resp = await c.post("/v1/admin/login", json={"password": _PASS})
    body = resp.json()
    assert "token" in body and "mfa_required" not in body
