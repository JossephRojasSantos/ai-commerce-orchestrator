"""Tests de señales del Product Scout: margen, velocidad, novedad, rank (T007)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from app.services.admin.scout import (
    compute_signals,
    margin_pct,
    upsert_snapshot,
    velocity_from_stocks,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DDL = """
CREATE TABLE IF NOT EXISTS scout_product_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dropi_product_id BIGINT NOT NULL,
    snapshot_date DATE NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    supplier_name TEXT,
    supplier_plan TEXT,
    cost_price NUMERIC NOT NULL,
    suggested_price NUMERIC,
    stock_total INTEGER DEFAULT 0,
    description_excerpt TEXT,
    dropi_created_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dropi_product_id, snapshot_date)
);
CREATE TABLE IF NOT EXISTS scout_signal (
    dropi_product_id BIGINT PRIMARY KEY,
    margin_pct NUMERIC,
    velocity_7d NUMERIC,
    is_novelty BOOLEAN DEFAULT 0,
    is_viable BOOLEAN DEFAULT 1,
    rank_score NUMERIC,
    last_seen_date DATE,
    computed_at DATETIME
)
"""


@pytest.fixture
async def scout_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for stmt in _DDL.strip().split(";"):
            if stmt.strip():
                await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


def _product(pid=1, name="Freidora aire 4L", cost=50000, suggested=99900, stock=100):
    return {
        "id": pid,
        "name": name,
        "sale_price": cost,
        "suggested_price": suggested,
        "description": "<p>Cocina sin aceite</p>",
        "categories": [{"name": "Hogar"}],
        "user": {"name": "Andres", "store_name": None, "plan": {"name": "SUPPLIER PREMIUM"}},
        "warehouse_product": [{"stock": stock}],
    }


# --- funciones puras ---


def test_margin_pct_with_freight():
    # (99900 - 50000 - 12000) / 99900 = 37.94%
    assert margin_pct(99900, 50000, 12000) == pytest.approx(37.94, abs=0.01)


def test_margin_negative_and_none():
    assert margin_pct(35000, 30000, 12000) < 0  # no viable
    assert margin_pct(None, 30000) is None
    assert margin_pct(0, 30000) is None


def test_margin_zero_freight():
    assert margin_pct(100000, 50000, 0) == pytest.approx(50.0)


def test_velocity_basic_drop():
    today = date(2026, 6, 13)
    stocks = [(today - timedelta(days=1), 150), (today, 120)]
    assert velocity_from_stocks(stocks) == 30.0


def test_velocity_restock_not_negative():
    today = date(2026, 6, 13)
    stocks = [(today - timedelta(days=1), 120), (today, 150)]
    assert velocity_from_stocks(stocks) == 0.0


def test_velocity_needs_two_days():
    assert velocity_from_stocks([(date(2026, 6, 13), 100)]) is None


def test_velocity_average_over_window():
    d = date(2026, 6, 13)
    # 100→90 (10), 90→95 restock (0), 95→65 (30) → media 13.33
    stocks = [
        (d - timedelta(days=3), 100),
        (d - timedelta(days=2), 90),
        (d - timedelta(days=1), 95),
        (d, 65),
    ]
    assert velocity_from_stocks(stocks) == pytest.approx(13.33, abs=0.01)


# --- snapshots + señales con DB ---


@pytest.mark.asyncio
async def test_upsert_same_day_no_duplicate(scout_db):
    today = date(2026, 6, 13)
    await upsert_snapshot(scout_db, _product(stock=100), today)
    await upsert_snapshot(scout_db, _product(stock=80), today)  # 2ª ejecución mismo día
    await scout_db.commit()
    rows = (
        await scout_db.execute(
            text("SELECT count(*), max(stock_total) FROM scout_product_snapshot")
        )
    ).one()
    assert rows[0] == 1  # FR-002: sin duplicado
    assert rows[1] == 80  # actualizado


@pytest.mark.asyncio
async def test_upsert_does_not_touch_previous_days(scout_db):
    today = date(2026, 6, 13)
    await upsert_snapshot(scout_db, _product(stock=150), today - timedelta(days=1))
    await upsert_snapshot(scout_db, _product(stock=120), today)
    await scout_db.commit()
    prev = (
        await scout_db.execute(
            text("SELECT stock_total FROM scout_product_snapshot WHERE snapshot_date < :d"),
            {"d": today},
        )
    ).scalar()
    assert prev == 150  # histórico intacto (FR-015)


@pytest.mark.asyncio
async def test_compute_signals_velocity_and_margin(scout_db, monkeypatch):
    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    await upsert_snapshot(scout_db, _product(stock=150), today - timedelta(days=1))
    await upsert_snapshot(scout_db, _product(stock=120), today)
    await scout_db.commit()

    n = await compute_signals(scout_db)
    assert n == 1
    row = (
        await scout_db.execute(text("SELECT velocity_7d, margin_pct, is_viable FROM scout_signal"))
    ).one()
    assert float(row[0]) == 30.0  # quickstart escenario 2
    assert float(row[1]) == pytest.approx(37.94, abs=0.01)
    assert bool(row[2]) is True


@pytest.mark.asyncio
async def test_compute_signals_nonviable_margin(scout_db, monkeypatch):
    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    await upsert_snapshot(
        scout_db, _product(pid=2, cost=30000, suggested=35000), today
    )  # margen negativo tras flete
    await scout_db.commit()
    await compute_signals(scout_db)
    row = (
        await scout_db.execute(
            text("SELECT is_viable, rank_score FROM scout_signal WHERE dropi_product_id=2")
        )
    ).one()
    assert bool(row[0]) is False  # FR-005
    assert float(row[1]) == 0.0


@pytest.mark.asyncio
async def test_compute_signals_novelty(scout_db, monkeypatch):
    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    product = _product(pid=3, stock=120)
    await upsert_snapshot(scout_db, product, today)
    # fija dropi_created_at reciente (sqlite guarda naive — el servicio normaliza)
    await scout_db.execute(
        text("UPDATE scout_product_snapshot SET dropi_created_at=:dt WHERE dropi_product_id=3"),
        {"dt": datetime.now(UTC) - timedelta(days=3)},
    )
    await scout_db.commit()
    await compute_signals(scout_db)
    row = (
        await scout_db.execute(text("SELECT is_novelty FROM scout_signal WHERE dropi_product_id=3"))
    ).one()
    assert bool(row[0]) is True  # FR-006


@pytest.mark.asyncio
async def test_compute_signals_batches_large_insert(scout_db, monkeypatch):
    """>2000 productos: el insert de señales se trocea (límite 32767 params asyncpg)."""
    from app.services.admin import scout as scout_mod

    today = date(2026, 6, 13)
    monkeypatch.setattr(scout_mod, "business_today", lambda: today)
    for pid in range(1, 2101):  # 2100 > chunk de 2000
        await upsert_snapshot(scout_db, _product(pid=pid), today)
    await scout_db.commit()

    n = await compute_signals(scout_db)
    assert n == 2100
    total = (await scout_db.execute(text("SELECT count(*) FROM scout_signal"))).scalar()
    assert total == 2100


def test_margin_pct_clamped_to_column_range():
    # precio sugerido ínfimo vs costo enorme → margen extremo, debe clampar a -9999.99
    m = margin_pct(100, 500000, 12000)
    assert m == -9999.99  # cabe en NUMERIC(6,2), no desborda
    # margen viable normal sin tocar
    assert margin_pct(99900, 50000, 12000) == pytest.approx(37.94, abs=0.01)


def test_dropi_product_url_includes_slug():
    from app.services.admin.scout import dropi_product_url

    u = dropi_product_url(497428, "MOTO 49CC")
    assert u == "https://app.dropi.co/dashboard/product-details/497428/moto-49cc"
    # tildes y signos
    u2 = dropi_product_url(5, "Pulidor de Uñas Eléctrico (2 en 1)")
    assert u2.endswith("/5/pulidor-de-unas-electrico-2-en-1")
    assert dropi_product_url(9, "").endswith("/9/producto")  # nombre vacío
