"""Tests de sesiones admin con Redis falso + endpoints restantes (cobertura T006/T023)."""

import uuid
from datetime import datetime
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from app.core import admin_auth
from fastapi import HTTPException


@pytest.fixture
def fake_redis_auth():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.core.admin_auth._redis", return_value=redis):
        yield redis


class _Req:
    class client:
        host = "1.2.3.4"


@pytest.mark.asyncio
async def test_session_lifecycle(fake_redis_auth):
    token = await admin_auth.create_session("1.2.3.4")
    assert token

    # sesión válida renueva TTL
    result = await admin_auth.require_admin_session(_Req(), authorization=f"Bearer {token}")
    assert result == token

    await admin_auth.destroy_session(token)
    with pytest.raises(HTTPException) as exc:
        await admin_auth.require_admin_session(_Req(), authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_scheme_rejected(fake_redis_auth):
    with pytest.raises(HTTPException):
        await admin_auth.require_admin_session(_Req(), authorization="Basic abc")


@pytest.mark.asyncio
async def test_login_failures_block_ip(fake_redis_auth):
    ip = "9.9.9.9"
    assert await admin_auth.check_login_blocked(ip) is False
    for _ in range(5):
        await admin_auth.register_login_failure(ip)
    assert await admin_auth.check_login_blocked(ip) is True


@pytest.mark.asyncio
async def test_create_session_clears_failures(fake_redis_auth):
    ip = "8.8.8.8"
    await admin_auth.register_login_failure(ip)
    await admin_auth.create_session(ip)
    assert await fake_redis_auth.get("admin_login_fail:" + ip) is None


@pytest.mark.asyncio
async def test_logout_and_me_endpoints(admin_client):
    with patch("app.routers.admin.destroy_session") as mock_destroy:
        mock_destroy.return_value = None

        async def _noop(token):
            return None

        mock_destroy.side_effect = _noop
        me = await admin_client.get("/v1/admin/me", headers={"Authorization": "Bearer t"})
        out = await admin_client.post("/v1/admin/logout", headers={"Authorization": "Bearer t"})
    assert me.status_code == 200
    assert out.status_code == 200 and out.json() == {"ok": True}


class _FakeScalarResult:
    def __init__(self, value):
        self._v = value

    def scalar(self):
        return self._v

    def scalar_one_or_none(self):
        return self._v

    def scalars(self):
        return self

    def all(self):
        return self._v


class _Conv:
    def __init__(self, sid):
        self.id = uuid.uuid4()
        self.session_id = sid
        self.created_at = datetime(2026, 6, 12, 10, 0)
        self.updated_at = self.created_at


class _Msg:
    def __init__(self, role, content, meta=None):
        self.role = role
        self.content = content
        self.created_at = datetime(2026, 6, 12, 10, 1)
        self.metadata_ = meta


@pytest.mark.asyncio
async def test_ai_conversations_list_and_detail(admin_client):
    sid = uuid.uuid4()
    conv = _Conv(sid)

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, *_a, **_k):
            self.calls += 1
            # lista: [convs], count, first | detalle: conv, msgs
            mapping = {
                1: _FakeScalarResult([conv]),
                2: _FakeScalarResult(2),
                3: _FakeScalarResult("hola"),
            }
            return mapping.get(self.calls, _FakeScalarResult([conv]))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("app.db.base.AsyncSessionLocal", return_value=FakeDB()):
        resp = await admin_client.get(
            "/v1/admin/ai/conversations", headers={"Authorization": "Bearer t"}
        )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["messages"] == 2
    assert items[0]["first_message"] == "hola"

    class FakeDetailDB(FakeDB):
        async def execute(self, *_a, **_k):
            self.calls += 1
            if self.calls == 1:
                return _FakeScalarResult(conv)
            return _FakeScalarResult(
                [_Msg("user", "hola"), _Msg("assistant", "respuesta", {"intent": "other"})]
            )

    with patch("app.db.base.AsyncSessionLocal", return_value=FakeDetailDB()):
        detail = await admin_client.get(
            f"/v1/admin/ai/conversations/{sid}", headers={"Authorization": "Bearer t"}
        )
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assert msgs[1]["intent"] == "other"

    bad = await admin_client.get(
        "/v1/admin/ai/conversations/no-es-uuid", headers={"Authorization": "Bearer t"}
    )
    assert bad.status_code == 404
