"""Scoring LLM de aptitud contraentrega para el top-N del Scout (feature 014, R4)."""

import hashlib
import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from app.config import settings
from app.models.scout import ScoutAiScore, ScoutIngestRun, ScoutSignal, ScoutSnapshot

logger = structlog.get_logger()

SCORE_LOCK_KEY = "scout:score_lock"
SCORE_LOCK_TTL = 900
BATCH_SIZE = 10

_PROMPT = """Eres un experto en venta contraentrega (COD) en Colombia.
Evalúa cada producto del JSON con score 0-100 según estos criterios:
- Compra por impulso (¿se antoja al verlo?)
- Problema-solución claro
- Fácil de demostrar visualmente (foto/video)
- Precio sugerido atractivo para COD: entre {price_min} y {price_max} COP

Responde SOLO un array JSON: [{{"id": <id>, "score": <0-100>, "reason": "<máx 150 caracteres, español>"}}]

Productos:
{products}"""


def content_hash(name: str, suggested_price, category: str | None, description: str | None) -> str:
    """Huella del contenido evaluado — si no cambia, se reusa el score (FR-009)."""
    raw = f"{name}|{suggested_price}|{category}|{(description or '')[:500]}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _top_candidates(db, top_n: int) -> list[dict]:
    max_date = (
        await db.execute(
            select(ScoutSignal.last_seen_date).order_by(ScoutSignal.last_seen_date.desc()).limit(1)
        )
    ).scalar()
    if max_date is None:
        return []
    rows = (
        await db.execute(
            select(ScoutSignal, ScoutSnapshot)
            .join(
                ScoutSnapshot,
                (ScoutSnapshot.dropi_product_id == ScoutSignal.dropi_product_id)
                & (ScoutSnapshot.snapshot_date == ScoutSignal.last_seen_date),
            )
            .where(ScoutSignal.last_seen_date == max_date, ScoutSignal.is_viable.is_(True))
            .order_by(ScoutSignal.rank_score.desc().nullslast())
            .limit(top_n)
        )
    ).all()
    return [
        {
            "id": snap.dropi_product_id,
            "name": snap.name,
            "category": snap.category,
            "suggested_price": float(snap.suggested_price) if snap.suggested_price else None,
            "description": snap.description_excerpt,
            "hash": content_hash(
                snap.name, snap.suggested_price, snap.category, snap.description_excerpt
            ),
        }
        for _, snap in rows
    ]


def _parse_llm_scores(raw: str) -> list[dict]:
    """Valida la salida del modelo: score 0-100 entero, razón ≤ 200 chars."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.startswith("json") else text
    items = json.loads(text)
    out = []
    for it in items:
        try:
            score = int(it["score"])
            pid = int(it["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= score <= 100:
            continue  # fuera de rango se descarta
        out.append({"id": pid, "score": score, "reason": str(it.get("reason") or "")[:200]})
    return out


async def run_scoring() -> dict:
    """Evalúa con el LLM los top-N candidatos sin score vigente (FR-008/009/010)."""
    from app.clients.llm import chat_complete
    from app.db.base import AsyncSessionLocal
    from app.services.admin.scout import _insert

    processed = failed = 0
    async with AsyncSessionLocal() as db:
        run = ScoutIngestRun(kind="score", status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    status, error_msg = "ok", None
    try:
        async with AsyncSessionLocal() as db:
            candidates = await _top_candidates(db, settings.SCOUT_TOP_N)

            # reuso por huella: solo se evalúa lo que cambió (FR-009)
            existing = {
                r.dropi_product_id: r.content_hash
                for r in (await db.execute(select(ScoutAiScore))).scalars().all()
            }
            pending = [c for c in candidates if existing.get(c["id"]) != c["hash"]]

            for i in range(0, len(pending), BATCH_SIZE):
                batch = pending[i : i + BATCH_SIZE]
                prompt = _PROMPT.format(
                    price_min=settings.SCOUT_PRICE_MIN,
                    price_max=settings.SCOUT_PRICE_MAX,
                    products=json.dumps(
                        [
                            {
                                k: c[k]
                                for k in (
                                    "id",
                                    "name",
                                    "category",
                                    "suggested_price",
                                    "description",
                                )
                            }
                            for c in batch
                        ],
                        ensure_ascii=False,
                    ),
                )
                try:
                    raw = await chat_complete([{"role": "user", "content": prompt}])
                    scores = _parse_llm_scores(raw)
                except Exception as exc:  # noqa: BLE001 — fallo LLM no rompe el ranking (FR-010)
                    failed += len(batch)
                    logger.warning("scout.score_batch_failed", error=str(exc))
                    continue
                hashes = {c["id"]: c["hash"] for c in batch}
                for s in scores:
                    if s["id"] not in hashes:
                        continue
                    values = {
                        "dropi_product_id": s["id"],
                        "score": s["score"],
                        "reason": s["reason"],
                        "content_hash": hashes[s["id"]],
                        "model": settings.LLM_MODEL_CHAT,
                        "scored_at": datetime.now(UTC),
                    }
                    stmt = _insert(db)(ScoutAiScore).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["dropi_product_id"],
                        set_={k: v for k, v in values.items() if k != "dropi_product_id"},
                    )
                    await db.execute(stmt)
                    processed += 1
                await db.commit()
    except Exception as exc:  # noqa: BLE001
        status, error_msg = "error", str(exc)[:500]
        logger.error("scout.score_failed", error=str(exc))

    async with AsyncSessionLocal() as db:
        run = await db.get(ScoutIngestRun, run_id)
        run.status = status
        run.processed = processed
        run.failed = failed
        run.error = error_msg
        run.finished_at = datetime.now(UTC)
        await db.commit()

    return {"status": status, "processed": processed, "failed": failed, "run_id": run_id}


async def run_scoring_locked() -> dict | None:
    """Variante con lock Redis; None si ya hay un scoring corriendo (FR-016)."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        acquired = await r.set(SCORE_LOCK_KEY, "1", nx=True, ex=SCORE_LOCK_TTL)
        if not acquired:
            return None
        try:
            return await run_scoring()
        finally:
            await r.delete(SCORE_LOCK_KEY)
    finally:
        await r.aclose()
