"""Tests E2E de los workers Scout sobre sqlite (cobertura run_ingest/score/demand)."""

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .test_scout_api import _AI_DDL
from .test_scout_demand import _DEMAND_DDL
from .test_scout_signals import _DDL, _product


@pytest.fixture
async def scout_factory():
    """Engine sqlite con TODAS las tablas scout y un sessionmaker parchable."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for stmt in (_DDL + ";" + _AI_DDL + ";" + _DEMAND_DDL).strip().split(";"):
            if stmt.strip():
                await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_ingest_happy_path(scout_factory, monkeypatch):
    """Pagina, deduplica, registra run ok y calcula señales (FR-001/002/015)."""
    from app.config import settings
    from app.workers import scout_ingest

    pages = [
        [_product(pid=1, stock=100), _product(pid=2, stock=50)],
        [_product(pid=2, stock=50)],  # duplicado entre páginas
        [],
    ]
    calls = {"n": 0}

    async def fake_list_products(start, category_id=None):
        out = pages[min(calls["n"], len(pages) - 1)]
        calls["n"] += 1
        return out

    with (
        patch("app.db.base.AsyncSessionLocal", scout_factory),
        patch.object(scout_ingest.dropi, "list_products", side_effect=fake_list_products),
        patch.object(settings, "DROPI_INTEGRATION_KEY", "tok"),
    ):
        result = await scout_ingest.run_ingest()

    assert result["status"] == "ok"
    assert result["processed"] == 2  # dedup
    async with scout_factory() as db:
        snaps = (await db.execute(text("SELECT count(*) FROM scout_product_snapshot"))).scalar()
        run = (
            await db.execute(text("SELECT status, processed, finished_at FROM scout_ingest_run"))
        ).one()
        signals = (await db.execute(text("SELECT count(*) FROM scout_signal"))).scalar()
    assert snaps == 2
    assert run[0] == "ok" and run[1] == 2 and run[2] is not None
    assert signals == 2


@pytest.mark.asyncio
async def test_run_ingest_partial_failure_marks_error(scout_factory, monkeypatch):
    """Fallo del proveedor a mitad → run error, snapshots previos intactos (FR-015)."""
    from app.config import settings
    from app.workers import scout_ingest

    async def fail(start, category_id=None):
        raise RuntimeError("dropi 500")

    with (
        patch("app.db.base.AsyncSessionLocal", scout_factory),
        patch.object(scout_ingest.dropi, "list_products", side_effect=fail),
        patch.object(settings, "DROPI_INTEGRATION_KEY", "tok"),
    ):
        result = await scout_ingest.run_ingest()
    assert result["status"] == "error"
    async with scout_factory() as db:
        run = (await db.execute(text("SELECT status, error FROM scout_ingest_run"))).one()
    assert run[0] == "error" and "dropi 500" in run[1]


@pytest.mark.asyncio
async def test_run_scoring_happy_path_and_hash_reuse(scout_factory, monkeypatch):
    """Top-N evaluado con LLM mock; 2ª corrida sin cambios → 0 llamadas (FR-008/009)."""
    from app.services.admin import scout as scout_mod
    from app.services.admin import scout_score

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    async with scout_factory() as db:
        for pid in (1, 2):
            await scout_mod.upsert_snapshot(
                db, _product(pid=pid, name=f"Prod {pid}"), today - timedelta(days=1)
            )
            await scout_mod.upsert_snapshot(db, _product(pid=pid, name=f"Prod {pid}"), today)
        await db.commit()
        await scout_mod.compute_signals(db)

    llm_calls = {"n": 0}

    async def fake_llm(messages, **kw):
        llm_calls["n"] += 1
        return json.dumps(
            [{"id": 1, "score": 80, "reason": "Impulso"}, {"id": 2, "score": 60, "reason": "Ok"}]
        )

    with (
        patch("app.db.base.AsyncSessionLocal", scout_factory),
        patch("app.clients.llm.chat_complete", side_effect=fake_llm),
    ):
        r1 = await scout_score.run_scoring()
        r2 = await scout_score.run_scoring()  # contenido sin cambios

    assert r1["status"] == "ok" and r1["processed"] == 2
    assert r2["processed"] == 0  # reuso por hash
    assert llm_calls["n"] == 1  # solo la 1ª corrida llamó al modelo
    async with scout_factory() as db:
        scores = (
            await db.execute(text("SELECT dropi_product_id, score FROM scout_ai_score ORDER BY 1"))
        ).all()
    assert [(s[0], s[1]) for s in scores] == [(1, 80), (2, 60)]


@pytest.mark.asyncio
async def test_run_scoring_llm_batch_failure_keeps_ranking(scout_factory, monkeypatch):
    """Fallo LLM en el lote → run ok con failed>0 y sin scores (FR-010)."""
    from app.services.admin import scout as scout_mod
    from app.services.admin import scout_score

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    async with scout_factory() as db:
        await scout_mod.upsert_snapshot(db, _product(pid=1), today)
        await db.commit()
        await scout_mod.compute_signals(db)

    async def boom(messages, **kw):
        raise RuntimeError("llm down")

    with (
        patch("app.db.base.AsyncSessionLocal", scout_factory),
        patch("app.clients.llm.chat_complete", side_effect=boom),
    ):
        result = await scout_score.run_scoring()
    assert result["status"] == "ok" and result["failed"] == 1
    async with scout_factory() as db:
        n = (await db.execute(text("SELECT count(*) FROM scout_ai_score"))).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_run_demand_analysis_happy_path(scout_factory, monkeypatch):
    """Extracción LLM + match catálogos + persistencia (FR-011/012, SC-006)."""
    from app.services.admin import scout_demand

    today = date(2026, 6, 13)
    async with scout_factory() as db:
        from app.services.admin.scout import upsert_snapshot

        await upsert_snapshot(db, _product(pid=9, name="Freidora de aire 5L"), today)
        await db.commit()

    async def fake_msgs(db):
        return [
            ("whatsapp", "hola, tienen freidora de aire?"),
            ("web", "quiero una gorra"),
            ("web", "donde esta mi pedido?"),  # tracking — el LLM lo ignora
        ]

    async def fake_llm(messages, **kw):
        return json.dumps(
            [
                {"term": "freidora de aire", "count": 1, "channels": ["whatsapp"]},
                {"term": "gorra", "count": 1, "channels": ["web"]},
            ]
        )

    with (
        patch("app.db.base.AsyncSessionLocal", scout_factory),
        patch.object(scout_demand, "_customer_messages", side_effect=fake_msgs),
        patch("app.clients.llm.chat_complete", side_effect=fake_llm),
        patch.object(
            scout_demand, "_own_catalog_names", new=AsyncMock(return_value=["gorra"])
        ),
    ):
        result = await scout_demand.run_demand_analysis()

    assert result["status"] == "ok" and result["processed"] == 2
    async with scout_factory() as db:
        unmet = await scout_demand.list_unmet_demand(db)
    assert [t["term"] for t in unmet["terms"]] == ["freidora de aire"]  # gorra matchea propio
    assert unmet["terms"][0]["dropi_candidates"][0]["dropi_product_id"] == 9


@pytest.mark.asyncio
async def test_demand_and_score_locks():
    """Variantes _locked devuelven None con lock tomado y liberan al terminar."""
    from app.services.admin import scout_demand, scout_score

    class TakenRedis:
        async def set(self, *a, **kw):
            return None

        async def delete(self, *a):
            pass

        async def aclose(self):
            pass

    with patch("redis.asyncio.from_url", return_value=TakenRedis()):
        assert await scout_score.run_scoring_locked() is None
        assert await scout_demand.run_demand_locked() is None

    calls = {"delete": 0}

    class FreeRedis:
        async def set(self, *a, **kw):
            return True

        async def delete(self, *a):
            calls["delete"] += 1

        async def aclose(self):
            pass

    with (
        patch("redis.asyncio.from_url", return_value=FreeRedis()),
        patch.object(scout_score, "run_scoring", new=AsyncMock(return_value={"status": "ok"})),
        patch.object(
            scout_demand, "run_demand_analysis", new=AsyncMock(return_value={"status": "ok"})
        ),
    ):
        assert (await scout_score.run_scoring_locked())["status"] == "ok"
        assert (await scout_demand.run_demand_locked())["status"] == "ok"
    assert calls["delete"] == 2


@pytest.mark.asyncio
async def test_scout_runs_and_ranking_period_endpoints(scout_factory, monkeypatch, admin_client):
    """GET /scout/runs y ranking con period=30d (velocidad en vivo) + demand endpoints."""
    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    async with scout_factory() as db:
        await scout_mod.upsert_snapshot(db, _product(pid=1, stock=150), today - timedelta(days=2))
        await scout_mod.upsert_snapshot(db, _product(pid=1, stock=100), today)
        await db.commit()
        await scout_mod.compute_signals(db)
        await db.execute(
            text("INSERT INTO scout_ingest_run (kind, status, processed) VALUES ('ingest','ok',5)")
        )
        await db.commit()

    with patch("app.db.base.AsyncSessionLocal", scout_factory):
        runs = (await admin_client.get("/v1/admin/scout/runs")).json()
        assert runs["runs"][0]["kind"] == "ingest" and runs["runs"][0]["processed"] == 5

        ranking = (await admin_client.get("/v1/admin/scout/ranking?period=30d")).json()
        assert len(ranking["candidates"]) == 1
        assert ranking["candidates"][0]["velocity_7d"] == 50.0  # Δ entre snapshots consecutivos disponibles

        demand = (await admin_client.get("/v1/admin/scout/demand")).json()
        assert demand["terms"] == []

    with patch(
        "app.routers.admin._scout_lock_active", new=AsyncMock(return_value=True)
    ):
        for path in ["/v1/admin/scout/score", "/v1/admin/scout/demand/refresh"]:
            resp = await admin_client.post(path)
            assert resp.status_code == 409
