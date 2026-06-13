"""Tests de los endpoints /v1/admin/scout/* (T010)."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from app.main import app
from app.services.admin.scout import get_ranking, upsert_snapshot
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .test_scout_signals import _DDL, _product

_AI_DDL = """
CREATE TABLE IF NOT EXISTS scout_ai_score (
    dropi_product_id BIGINT PRIMARY KEY,
    score SMALLINT NOT NULL,
    reason VARCHAR(200) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    model TEXT,
    scored_at DATETIME
);
CREATE TABLE IF NOT EXISTS scout_ingest_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind VARCHAR(10) NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    status VARCHAR(10) DEFAULT 'running',
    processed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    error TEXT
)
"""


@pytest.fixture
async def scout_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for stmt in (_DDL + ";" + _AI_DDL).strip().split(";"):
            if stmt.strip():
                await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(db, monkeypatch):
    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    await upsert_snapshot(db, _product(pid=1, stock=150), today - timedelta(days=1))
    await upsert_snapshot(db, _product(pid=1, stock=120), today)
    await upsert_snapshot(
        db,
        _product(pid=2, name="Gorra", cost=30000, suggested=35000, stock=10),
        today,
    )  # margen negativo
    await db.commit()
    await scout_mod.compute_signals(db)
    return today


@pytest.mark.asyncio
async def test_ranking_excludes_nonviable_and_orders(scout_db, monkeypatch):
    await _seed(scout_db, monkeypatch)
    out = await get_ranking(scout_db)
    assert len(out["candidates"]) == 1  # no viable excluido (FR-005)
    c = out["candidates"][0]
    assert c["dropi_product_id"] == 1
    assert c["margin_pct"] == pytest.approx(37.94, abs=0.01)
    assert c["velocity_7d"] == 30.0
    assert c["ai"] is None  # sin evaluar (FR-010)
    # incluye id + slug del nombre (Dropi exige el slug, sin él redirige a /home)
    assert c["dropi_url"].endswith("/1/freidora-aire-4l")
    # FR-014: sin credenciales en el payload
    assert "token" not in str(out).lower() and "integration-key" not in str(out).lower()


@pytest.mark.asyncio
async def test_ranking_include_nonviable_and_category_filter(scout_db, monkeypatch):
    await _seed(scout_db, monkeypatch)
    all_out = await get_ranking(scout_db, include_nonviable=True)
    assert len(all_out["candidates"]) == 2
    filtered = await get_ranking(scout_db, category="Hogar")
    assert all(c["category"] == "Hogar" for c in filtered["candidates"])
    assert "Hogar" in all_out["categories"]


@pytest.mark.asyncio
async def test_ranking_empty_state(scout_db):
    out = await get_ranking(scout_db)
    assert out == {"computed_at": None, "candidates": [], "categories": []}


@pytest.mark.asyncio
async def test_ranking_includes_ai_score_when_present(scout_db, monkeypatch):
    await _seed(scout_db, monkeypatch)
    await scout_db.execute(
        text(
            "INSERT INTO scout_ai_score (dropi_product_id, score, reason, content_hash)"
            " VALUES (1, 78, 'Compra por impulso', 'h')"
        )
    )
    await scout_db.commit()
    out = await get_ranking(scout_db)
    assert out["candidates"][0]["ai"] == {"score": 78, "reason": "Compra por impulso"}


@pytest.mark.asyncio
async def test_scout_endpoints_require_session():
    bad = {"Authorization": "Basic nope"}  # scheme inválido → 401 antes de tocar Redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ["/v1/admin/scout/ranking", "/v1/admin/scout/runs"]:
            resp = await client.get(path, headers=bad)
            assert resp.status_code == 401
        resp = await client.post("/v1/admin/scout/ingest", headers=bad)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_endpoint_409_when_locked(admin_client):
    with patch("app.routers.admin._scout_lock_active", new=AsyncMock(return_value=True)):
        resp = await admin_client.post("/v1/admin/scout/ingest")
    assert resp.status_code == 409
    assert resp.json()["message"] == "already_running"  # ErrorResponse del handler global


@pytest.mark.asyncio
async def test_ingest_endpoint_202_launches_background(admin_client):
    launched = {}

    async def fake_run():
        launched["yes"] = True

    with (
        patch("app.routers.admin._scout_lock_active", new=AsyncMock(return_value=False)),
        patch("app.workers.scout_ingest.run_ingest_locked", side_effect=fake_run),
    ):
        resp = await admin_client.post("/v1/admin/scout/ingest")
        import asyncio

        await asyncio.sleep(0)
    assert resp.status_code == 202
    assert resp.json()["status"] == "running"
    assert launched.get("yes") is True


@pytest.mark.asyncio
async def test_ranking_search_multi_term(scout_db, monkeypatch):
    from datetime import date

    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    await upsert_snapshot(scout_db, _product(pid=1, name="Lampara Solar Jardin", cost=20000, suggested=99900), today)
    await upsert_snapshot(scout_db, _product(pid=2, name="Audifonos Gamer BT", cost=30000, suggested=99900), today)
    await scout_db.commit()
    await scout_mod.compute_signals(scout_db)

    # ambos términos deben aparecer (AND) → solo la lámpara
    out = await get_ranking(scout_db, search="lampara solar")
    assert [c["dropi_product_id"] for c in out["candidates"]] == [1]
    # término en categoría/nombre, may/min indiferente
    out2 = await get_ranking(scout_db, search="GAMER")
    assert [c["dropi_product_id"] for c in out2["candidates"]] == [2]
    # sin coincidencia
    out3 = await get_ranking(scout_db, search="bicicleta")
    assert out3["candidates"] == []
