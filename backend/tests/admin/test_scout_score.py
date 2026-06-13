"""Tests del scoring IA del Scout: top-N, reuso por hash, fallos LLM (T013)."""

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from app.services.admin.scout import compute_signals, upsert_snapshot
from app.services.admin.scout_score import _parse_llm_scores, _top_candidates, content_hash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .test_scout_api import _AI_DDL
from .test_scout_signals import _DDL, _product


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


def test_content_hash_stable_and_sensitive():
    h1 = content_hash("Freidora", 99900, "Hogar", "desc")
    assert h1 == content_hash("Freidora", 99900, "Hogar", "desc")  # estable
    assert h1 != content_hash("Freidora", 89900, "Hogar", "desc")  # precio cambia ⇒ re-evaluar


def test_parse_llm_scores_valid_and_invalid():
    raw = json.dumps(
        [
            {"id": 1, "score": 78, "reason": "Compra por impulso"},
            {"id": 2, "score": 150, "reason": "fuera de rango"},  # descartado
            {"id": 3, "score": -5, "reason": "negativo"},  # descartado
            {"id": "x", "score": 50, "reason": "id inválido"},  # descartado
            {"id": 4, "score": 60, "reason": "R" * 300},  # razón truncada
        ]
    )
    out = _parse_llm_scores(raw)
    assert [s["id"] for s in out] == [1, 4]
    assert len(out[1]["reason"]) == 200


def test_parse_llm_scores_markdown_fences():
    raw = '```json\n[{"id": 1, "score": 50, "reason": "ok"}]\n```'
    assert _parse_llm_scores(raw)[0]["score"] == 50


async def _seed(db, monkeypatch, n=3):
    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    for pid in range(1, n + 1):
        await upsert_snapshot(
            db, _product(pid=pid, name=f"Prod {pid}", stock=100 + pid * 10), today - timedelta(days=1)
        )
        await upsert_snapshot(db, _product(pid=pid, name=f"Prod {pid}", stock=80), today)
    await db.commit()
    await compute_signals(db)
    return today


@pytest.mark.asyncio
async def test_top_candidates_respects_limit(scout_db, monkeypatch):
    await _seed(scout_db, monkeypatch, n=5)
    top = await _top_candidates(scout_db, 2)
    assert len(top) == 2  # solo top-N va al LLM (FR-008)
    assert all("hash" in c for c in top)


@pytest.mark.asyncio
async def test_scoring_skips_unchanged_hash(scout_db, monkeypatch):
    """Hash vigente ⇒ candidato no se reenvía al modelo (FR-009)."""
    await _seed(scout_db, monkeypatch, n=2)
    top = await _top_candidates(scout_db, 10)
    # simula score previo con el hash actual del candidato 1
    await scout_db.execute(
        text(
            "INSERT INTO scout_ai_score (dropi_product_id, score, reason, content_hash)"
            " VALUES (:pid, 70, 'previo', :h)"
        ),
        {"pid": top[0]["id"], "h": top[0]["hash"]},
    )
    await scout_db.commit()

    from app.models.scout import ScoutAiScore
    from sqlalchemy import select

    existing = {
        r.dropi_product_id: r.content_hash
        for r in (await scout_db.execute(select(ScoutAiScore))).scalars().all()
    }
    pending = [c for c in top if existing.get(c["id"]) != c["hash"]]
    assert top[0]["id"] not in [c["id"] for c in pending]
    assert len(pending) == len(top) - 1


@pytest.mark.asyncio
async def test_run_scoring_llm_failure_is_besteffort():
    """Fallo del LLM ⇒ run error/ok parcial, jamás excepción al caller (FR-010)."""
    from app.services.admin import scout_score

    class FakeRun:
        id = 1
        status = processed = failed = error = finished_at = None

    fake_db = AsyncMock()
    fake_db.__aenter__.return_value = fake_db
    fake_db.add = lambda obj: None
    fake_db.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", 1))
    fake_db.get = AsyncMock(return_value=FakeRun())

    with (
        patch("app.db.base.AsyncSessionLocal", return_value=fake_db),
        patch.object(scout_score, "_top_candidates", new=AsyncMock(side_effect=RuntimeError("db down"))),
    ):
        result = await scout_score.run_scoring()
    assert result["status"] == "error"
    assert result["processed"] == 0
