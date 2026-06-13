"""Tests de demanda insatisfecha: normalización, matching, candidatos Dropi (T017)."""

import json
from datetime import date

import pytest
from app.services.admin.scout import upsert_snapshot
from app.services.admin.scout_demand import (
    _dropi_candidates,
    _parse_terms,
    list_unmet_demand,
    matches_own_catalog,
    normalize_term,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .test_scout_signals import _DDL, _product

_DEMAND_DDL = """
CREATE TABLE IF NOT EXISTS scout_demand_term (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT UNIQUE NOT NULL,
    mention_count INTEGER DEFAULT 1,
    sample_channels JSON,
    matched_own_catalog BOOLEAN DEFAULT 0,
    dropi_candidates JSON,
    analyzed_at DATETIME
)
"""


@pytest.fixture
async def scout_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for stmt in (_DDL + ";" + _DEMAND_DDL).strip().split(";"):
            if stmt.strip():
                await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


def test_normalize_term():
    assert normalize_term("  Freidora de Aire ") == "freidora de aire"
    assert normalize_term("Depilación  Láser") == "depilacion laser"


def test_parse_terms_filters_invalid():
    raw = json.dumps(
        [
            {"term": "Freidora de aire", "count": 4, "channels": ["whatsapp"]},
            {"term": "", "count": 1, "channels": ["web"]},  # vacío fuera
            {"term": "gorra", "count": "x", "channels": ["telegram"]},  # canal inválido → web
        ]
    )
    out = _parse_terms(raw)
    assert out[0] == {"term": "freidora de aire", "count": 4, "channels": ["whatsapp"]}
    assert len(out) == 2
    assert out[1]["channels"] == ["web"] and out[1]["count"] == 1


def test_parse_terms_empty_when_no_products():
    # saludos/tracking ⇒ el modelo responde [] y no se generan términos (SC-006)
    assert _parse_terms("[]") == []


def test_matches_own_catalog_bidirectional():
    own = [normalize_term("Freidora de Aire Digital 4L"), normalize_term("Gorra")]
    assert matches_own_catalog("freidora de aire", own) is True  # término ⊂ nombre
    assert matches_own_catalog("gorra deportiva premium", own) is True  # nombre ⊂ término
    assert matches_own_catalog("masajeador cervical", own) is False


@pytest.mark.asyncio
async def test_dropi_candidates_ilike(scout_db):
    today = date(2026, 6, 13)
    await upsert_snapshot(scout_db, _product(pid=1, name="Freidora de aire 5L premium"), today)
    await upsert_snapshot(scout_db, _product(pid=2, name="Gorra unisex"), today)
    await scout_db.commit()
    out = await _dropi_candidates(scout_db, "freidora de aire")
    assert [c["dropi_product_id"] for c in out] == [1]


@pytest.mark.asyncio
async def test_list_unmet_demand_excludes_matched(scout_db):
    await scout_db.execute(
        text(
            "INSERT INTO scout_demand_term (term, mention_count, sample_channels, matched_own_catalog, dropi_candidates, analyzed_at)"
            " VALUES ('freidora de aire', 4, '[\"whatsapp\"]', 0, '[{\"dropi_product_id\": 1, \"name\": \"Freidora 5L\"}]', '2026-06-13 10:00:00'),"
            " ('gorra', 2, '[\"web\"]', 1, NULL, '2026-06-13 10:00:00')"
        )
    )
    await scout_db.commit()
    out = await list_unmet_demand(scout_db)
    assert len(out["terms"]) == 1  # el matcheado al catálogo propio se excluye (FR-011)
    t = out["terms"][0]
    assert t["term"] == "freidora de aire"
    assert t["mention_count"] == 4
    assert t["dropi_candidates"][0]["dropi_product_id"] == 1  # FR-012


_MSG_DDL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
);
CREATE TABLE IF NOT EXISTS wa_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    author TEXT NOT NULL,
    content TEXT NOT NULL,
    delivered BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


@pytest.fixture
async def msg_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for stmt in _MSG_DDL.strip().split(";"):
            if stmt.strip():
                await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_customer_messages_both_channels(msg_db):
    from app.services.admin.scout_demand import _customer_messages

    await msg_db.execute(
        text(
            "INSERT INTO messages (id, role, content, created_at) VALUES"
            " ('m1', 'user', 'quiero una freidora', CURRENT_TIMESTAMP),"
            " ('m2', 'assistant', 'claro!', CURRENT_TIMESTAMP)"
        )
    )
    await msg_db.execute(
        text(
            "INSERT INTO wa_messages (id, author, content, created_at) VALUES"
            " ('w1', 'customer', 'tienen gorras?', CURRENT_TIMESTAMP),"
            " ('w2', 'bot', 'sí', CURRENT_TIMESTAMP)"
        )
    )
    await msg_db.commit()
    out = await _customer_messages(msg_db)
    assert ("web", "quiero una freidora") in out
    assert ("whatsapp", "tienen gorras?") in out
    assert len(out) == 2  # solo author/role de cliente


@pytest.mark.asyncio
async def test_own_catalog_names_normalized():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.admin.scout_demand import _own_catalog_names

    wc = MagicMock()
    wc.list_products_raw = AsyncMock(
        return_value=[{"name": "Freidora de Aire Digital"}, {"name": "Gorra Mágica"}]
    )
    with patch("app.clients.woocommerce.get_wc_client", new=AsyncMock(return_value=wc)):
        names = await _own_catalog_names()
    assert names == ["freidora de aire digital", "gorra magica"]
