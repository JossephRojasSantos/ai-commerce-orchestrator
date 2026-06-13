"""Señales y ranking del Product Scout (feature 014, research R3/R4)."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select

from app.config import settings
from app.models.scout import ScoutSignal, ScoutSnapshot

logger = structlog.get_logger()

VELOCITY_WINDOW_DAYS = 7


def _insert(db):
    """insert con ON CONFLICT del dialecto activo (postgres en prod, sqlite en tests)."""
    if db.get_bind().dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as ins
    else:
        from sqlalchemy.dialects.postgresql import insert as ins
    return ins


def business_today() -> date:
    """Fecha de negocio (Colombia, UTC-5) — los snapshots se agrupan por este día."""
    return datetime.now(ZoneInfo("America/Bogota")).date()


def margin_pct(suggested: float | None, cost: float, freight: int | None = None) -> float | None:
    """(sugerido − costo − flete) / sugerido × 100; None sin precio sugerido (FR-004)."""
    if not suggested or suggested <= 0:
        return None
    fr = settings.SCOUT_FREIGHT_COST if freight is None else freight
    pct = round((float(suggested) - float(cost) - fr) / float(suggested) * 100, 2)
    # margin_pct es NUMERIC(6,2): clamp a ±9999.99. Un margen viable está en 0-100%;
    # valores extremos solo ocurren en productos no viables (precio sugerido ínfimo).
    return max(-9999.99, min(9999.99, pct))


def velocity_from_stocks(stocks_by_date: list[tuple[date, int]]) -> float | None:
    """Media de max(0, Δstock) entre días consecutivos con datos (FR-003, R3).

    Restock (Δ>0) cuenta como día sin venta (0). None con < 2 snapshots.
    """
    if len(stocks_by_date) < 2:
        return None
    ordered = sorted(stocks_by_date)
    drops = [
        max(0, prev_stock - curr_stock)
        for (_, prev_stock), (_, curr_stock) in zip(ordered, ordered[1:], strict=False)
    ]
    return round(sum(drops) / len(drops), 2)


async def compute_signals(db) -> int:
    """Recalcula scout_signal para todos los productos con snapshots recientes.

    Devuelve el nº de señales escritas. Solo lee snapshots (histórico intacto).
    """
    today = business_today()
    window_start = today - timedelta(days=VELOCITY_WINDOW_DAYS)

    rows = (
        await db.execute(
            select(
                ScoutSnapshot.dropi_product_id,
                ScoutSnapshot.snapshot_date,
                ScoutSnapshot.stock_total,
                ScoutSnapshot.cost_price,
                ScoutSnapshot.suggested_price,
                ScoutSnapshot.dropi_created_at,
            ).where(ScoutSnapshot.snapshot_date >= window_start)
        )
    ).all()
    if not rows:
        return 0

    by_product: dict[int, list] = defaultdict(list)
    for r in rows:
        by_product[r.dropi_product_id].append(r)

    signals = []
    for pid, snaps in by_product.items():
        latest = max(snaps, key=lambda s: s.snapshot_date)
        m = margin_pct(latest.suggested_price, latest.cost_price)
        vel = velocity_from_stocks([(s.snapshot_date, s.stock_total) for s in snaps])
        is_novelty = bool(
            latest.dropi_created_at
            and _aware(latest.dropi_created_at)
            >= datetime.now(UTC) - timedelta(days=settings.SCOUT_NOVELTY_DAYS)
            and latest.stock_total >= settings.SCOUT_NOVELTY_STOCK
        )
        signals.append(
            {
                "dropi_product_id": pid,
                "margin_pct": m,
                "velocity_7d": vel,
                "is_novelty": is_novelty,
                "is_viable": m is not None and m > 0,  # FR-005
                "last_seen_date": latest.snapshot_date,
                "computed_at": datetime.now(UTC),
            }
        )

    # rank_score: min-max sobre el conjunto viable del día (data-model.md)
    viable = [s for s in signals if s["is_viable"]]
    margins = [s["margin_pct"] for s in viable]
    vels = [s["velocity_7d"] or 0.0 for s in viable]

    def norm(value: float, values: list[float]) -> float:
        lo, hi = min(values), max(values)
        return 0.5 if hi == lo else (value - lo) / (hi - lo)

    for s in signals:
        if not s["is_viable"]:
            s["rank_score"] = 0.0
            continue
        s["rank_score"] = round(
            0.5 * norm(s["margin_pct"], margins)
            + 0.4 * norm(s["velocity_7d"] or 0.0, vels)
            + 0.1 * (1.0 if s["is_novelty"] else 0.0),
            4,
        )

    # Insert por lotes: asyncpg limita a 32767 parámetros por query
    # (8 columnas × ~4000 filas), así que troceamos a 2000 filas/lote.
    cols = list(signals[0])
    chunk = 2000
    for i in range(0, len(signals), chunk):
        batch = signals[i : i + chunk]
        stmt = _insert(db)(ScoutSignal).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["dropi_product_id"],
            set_={c: stmt.excluded[c] for c in cols if c != "dropi_product_id"},
        )
        await db.execute(stmt)
    await db.commit()
    return len(signals)


async def upsert_snapshot(db, product: dict, snapshot_date: date) -> None:
    """Upsert del snapshot del día (UNIQUE dropi_product_id+snapshot_date — FR-002)."""
    from app.clients.dropi import first_category, stock_total

    user = product.get("user") or {}
    plan = (user.get("plan") or {}).get("name") if isinstance(user.get("plan"), dict) else None
    desc = _strip_html(product.get("description") or "")[:500] or None
    created_raw = product.get("created_at")
    dropi_created = _parse_dt(created_raw) if created_raw else None

    values = {
        "dropi_product_id": int(product["id"]),
        "snapshot_date": snapshot_date,
        "name": product.get("name") or "",
        "category": first_category(product),
        "supplier_name": user.get("store_name") or user.get("name"),
        "supplier_plan": plan,
        "cost_price": float(product.get("sale_price") or 0),
        "suggested_price": float(product["suggested_price"])
        if product.get("suggested_price")
        else None,
        "stock_total": stock_total(product),
        "description_excerpt": desc,
        "dropi_created_at": dropi_created,
    }
    stmt = _insert(db)(ScoutSnapshot).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["dropi_product_id", "snapshot_date"],
        set_={k: v for k, v in values.items() if k not in ("dropi_product_id", "snapshot_date")},
    )
    await db.execute(stmt)


def _aware(dt: datetime) -> datetime:
    """Normaliza datetimes naive (sqlite en tests) a UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _strip_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", text).replace("\xa0", " ").strip()


def _parse_dt(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


PERIOD_DAYS = {"today": 1, "7d": 7, "30d": 30}

DROPI_PRODUCT_URL = "https://app.dropi.co/dashboard/product-details/{id}/{slug}"


def _slugify(name: str) -> str:
    """Slug estilo Dropi: minúsculas, sin tildes, no-alfanumérico → guion.

    El detalle de producto de Dropi exige el slug en la URL; sin él redirige
    a /home (verificado en vivo). Se deriva del nombre del producto.
    """
    import re
    import unicodedata

    s = unicodedata.normalize("NFKD", (name or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "producto"


def dropi_product_url(product_id: int, name: str) -> str:
    return DROPI_PRODUCT_URL.format(id=product_id, slug=_slugify(name))


async def get_ranking(
    db,
    category: str | None = None,
    period: str = "7d",
    include_nonviable: bool = False,
    search: str | None = None,
    limit: int = 100,
) -> dict:
    """Ranking de candidatos: señales + último snapshot + score IA (FR-007/013).

    El DTO jamás incluye credenciales ni URLs internas del proveedor (FR-014).
    """
    from app.models.scout import ScoutAiScore

    max_date = (await db.execute(select(func.max(ScoutSignal.last_seen_date)))).scalar()
    if max_date is None:
        return {"computed_at": None, "candidates": [], "categories": []}

    q = (
        select(ScoutSignal, ScoutSnapshot, ScoutAiScore)
        .join(
            ScoutSnapshot,
            (ScoutSnapshot.dropi_product_id == ScoutSignal.dropi_product_id)
            & (ScoutSnapshot.snapshot_date == ScoutSignal.last_seen_date),
        )
        .outerjoin(ScoutAiScore, ScoutAiScore.dropi_product_id == ScoutSignal.dropi_product_id)
        .where(ScoutSignal.last_seen_date == max_date)  # inactivos fuera (edge case)
        .order_by(ScoutSignal.rank_score.desc().nullslast())
        .limit(limit)
    )
    if not include_nonviable:
        q = q.where(ScoutSignal.is_viable.is_(True))
    if category:
        q = q.where(ScoutSnapshot.category == category)
    if search and search.strip():
        # Búsqueda por términos: cada palabra debe aparecer en nombre o categoría
        # (AND entre términos, OR entre campos). Tolerante a may/min.
        for term in search.lower().split():
            like = f"%{term}%"
            q = q.where(
                func.lower(ScoutSnapshot.name).like(like)
                | func.lower(func.coalesce(ScoutSnapshot.category, "")).like(like)
            )

    rows = (await db.execute(q)).all()

    # velocidad del período pedido, calculada en vivo solo para los candidatos listados
    days = PERIOD_DAYS.get(period, 7)
    pids = [sig.dropi_product_id for sig, _, _ in rows]
    period_velocity: dict[int, float | None] = {}
    if pids and days != VELOCITY_WINDOW_DAYS:
        snaps = (
            await db.execute(
                select(
                    ScoutSnapshot.dropi_product_id,
                    ScoutSnapshot.snapshot_date,
                    ScoutSnapshot.stock_total,
                ).where(
                    ScoutSnapshot.dropi_product_id.in_(pids),
                    ScoutSnapshot.snapshot_date >= max_date - timedelta(days=days),
                )
            )
        ).all()
        grouped: dict[int, list] = defaultdict(list)
        for r in snaps:
            grouped[r.dropi_product_id].append((r.snapshot_date, r.stock_total))
        period_velocity = {pid: velocity_from_stocks(v) for pid, v in grouped.items()}

    candidates = []
    for sig, snap, ai in rows:
        vel = period_velocity.get(sig.dropi_product_id, sig.velocity_7d)
        candidates.append(
            {
                "dropi_product_id": sig.dropi_product_id,
                "name": snap.name,
                "category": snap.category,
                "supplier": snap.supplier_name,
                "cost_price": float(snap.cost_price),
                "suggested_price": float(snap.suggested_price) if snap.suggested_price else None,
                "margin_pct": float(sig.margin_pct) if sig.margin_pct is not None else None,
                "velocity_7d": float(vel) if vel is not None else None,
                "is_novelty": bool(sig.is_novelty),
                "is_viable": bool(sig.is_viable),
                "rank_score": float(sig.rank_score) if sig.rank_score is not None else None,
                "ai": {"score": ai.score, "reason": ai.reason} if ai else None,
                "dropi_url": dropi_product_url(sig.dropi_product_id, snap.name),
                "stock_total": snap.stock_total,
                "last_seen_date": str(sig.last_seen_date),
            }
        )

    cats = (
        (
            await db.execute(
                select(ScoutSnapshot.category)
                .where(ScoutSnapshot.snapshot_date == max_date, ScoutSnapshot.category.isnot(None))
                .distinct()
                .order_by(ScoutSnapshot.category)
            )
        )
        .scalars()
        .all()
    )

    computed = (await db.execute(select(func.max(ScoutSignal.computed_at)))).scalar()
    return {
        "computed_at": computed.isoformat() if computed else None,
        "candidates": candidates,
        "categories": list(cats),
    }


async def list_runs(db, limit: int = 10) -> list[dict]:
    """Últimas ejecuciones (ingest/score/demand) para diagnóstico (FR-015)."""
    from app.models.scout import ScoutIngestRun

    rows = (
        (await db.execute(select(ScoutIngestRun).order_by(ScoutIngestRun.id.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "status": r.status,
            "processed": r.processed,
            "failed": r.failed,
            "error": r.error,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in rows
    ]


async def latest_snapshot_count(db) -> int:
    today = business_today()
    return (
        await db.execute(
            select(func.count(ScoutSnapshot.id)).where(ScoutSnapshot.snapshot_date == today)
        )
    ).scalar() or 0
