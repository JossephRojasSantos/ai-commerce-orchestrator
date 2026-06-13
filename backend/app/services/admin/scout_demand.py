"""Demanda insatisfecha desde conversaciones web + WhatsApp (feature 014, R5)."""

import json
import unicodedata
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select

from app.models.scout import ScoutDemandTerm, ScoutIngestRun, ScoutSnapshot

logger = structlog.get_logger()

DEMAND_LOCK_KEY = "scout:demand_lock"
DEMAND_LOCK_TTL = 600
LOOKBACK_DAYS = 30
MAX_CANDIDATES = 5

_PROMPT = """De los siguientes mensajes de clientes de una tienda, extrae los productos
o tipos de producto que los clientes quieren COMPRAR. Ignora saludos, despedidas,
agradecimientos, seguimiento de pedidos ("dónde está mi pedido") y preguntas de envío.

Responde SOLO un array JSON: [{{"term": "<producto en singular, minúsculas>", "count": <nº de menciones>, "channels": ["web"|"whatsapp", ...]}}]
Si ningún mensaje pide productos, responde [].

Mensajes (formato canal: texto):
{messages}"""


def normalize_term(term: str) -> str:
    """minúsculas, sin tildes, espacios colapsados."""
    t = unicodedata.normalize("NFKD", term.lower().strip())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split())


async def _customer_messages(db) -> list[tuple[str, str]]:
    """[(canal, texto)] de los últimos LOOKBACK_DAYS (web + WhatsApp)."""
    from app.models.conversation import Message
    from app.models.wa_conversation import WaMessage

    since = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
    out: list[tuple[str, str]] = []

    web = (
        await db.execute(
            select(Message.content).where(Message.role == "user", Message.created_at >= since)
        )
    ).all()
    out.extend(("web", r.content) for r in web)

    wa = (
        await db.execute(
            select(WaMessage.content).where(
                WaMessage.author == "customer", WaMessage.created_at >= since
            )
        )
    ).all()
    out.extend(("whatsapp", r.content) for r in wa)
    return out


def _parse_terms(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.startswith("json") else text
    items = json.loads(text)
    out = []
    for it in items:
        term = normalize_term(str(it.get("term") or ""))
        if not term:
            continue
        channels = [c for c in (it.get("channels") or []) if c in ("web", "whatsapp")]
        try:
            count = max(1, int(it.get("count") or 1))
        except (TypeError, ValueError):
            count = 1
        out.append({"term": term, "count": count, "channels": channels or ["web"]})
    return out


async def _own_catalog_names() -> list[str]:
    """Nombres del catálogo WC propio, normalizados (server-side, FR-014)."""
    from app.clients.woocommerce import get_wc_client

    wc = await get_wc_client()
    products = await wc.list_products_raw()
    return [normalize_term(p.get("name") or "") for p in products]


def matches_own_catalog(term: str, own_names: list[str]) -> bool:
    """Match laxo bidireccional: término contenido en nombre o viceversa."""
    return any(term in name or name in term for name in own_names if name)


async def _dropi_candidates(db, term: str) -> list[dict]:
    max_date = (await db.execute(select(func.max(ScoutSnapshot.snapshot_date)))).scalar()
    if max_date is None:
        return []
    rows = (
        await db.execute(
            select(ScoutSnapshot.dropi_product_id, ScoutSnapshot.name)
            .where(
                ScoutSnapshot.snapshot_date == max_date,
                func.lower(ScoutSnapshot.name).like(f"%{term}%"),
            )
            .limit(MAX_CANDIDATES)
        )
    ).all()
    return [{"dropi_product_id": r.dropi_product_id, "name": r.name} for r in rows]


async def run_demand_analysis() -> dict:
    """Extrae términos con LLM, cruza catálogos y persiste (FR-011/012)."""
    from app.clients.llm import chat_complete
    from app.db.base import AsyncSessionLocal

    processed = failed = 0
    async with AsyncSessionLocal() as db:
        run = ScoutIngestRun(kind="demand", status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    status, error_msg = "ok", None
    try:
        async with AsyncSessionLocal() as db:
            messages = await _customer_messages(db)
            if messages:
                listing = "\n".join(f"{ch}: {txt[:200]}" for ch, txt in messages[:300])
                raw = await chat_complete([{"role": "user", "content": _PROMPT.format(messages=listing)}])
                terms = _parse_terms(raw)

                own_names = await _own_catalog_names()
                await db.execute(delete(ScoutDemandTerm))  # snapshot completo del análisis
                for t in terms:
                    matched = matches_own_catalog(t["term"], own_names)
                    db.add(
                        ScoutDemandTerm(
                            term=t["term"],
                            mention_count=t["count"],
                            sample_channels=t["channels"],
                            matched_own_catalog=matched,
                            dropi_candidates=(
                                await _dropi_candidates(db, t["term"]) if not matched else None
                            ),
                            analyzed_at=datetime.now(UTC),
                        )
                    )
                    processed += 1
                await db.commit()
    except Exception as exc:  # noqa: BLE001
        status, error_msg = "error", str(exc)[:500]
        logger.error("scout.demand_failed", error=str(exc))

    async with AsyncSessionLocal() as db:
        run = await db.get(ScoutIngestRun, run_id)
        run.status = status
        run.processed = processed
        run.failed = failed
        run.error = error_msg
        run.finished_at = datetime.now(UTC)
        await db.commit()

    return {"status": status, "processed": processed, "run_id": run_id}


async def run_demand_locked() -> dict | None:
    import redis.asyncio as aioredis

    from app.config import settings

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        acquired = await r.set(DEMAND_LOCK_KEY, "1", nx=True, ex=DEMAND_LOCK_TTL)
        if not acquired:
            return None
        try:
            return await run_demand_analysis()
        finally:
            await r.delete(DEMAND_LOCK_KEY)
    finally:
        await r.aclose()


async def list_unmet_demand(db) -> dict:
    """Términos sin match en catálogo propio (FR-011)."""
    rows = (
        (
            await db.execute(
                select(ScoutDemandTerm)
                .where(ScoutDemandTerm.matched_own_catalog.is_(False))
                .order_by(ScoutDemandTerm.mention_count.desc())
            )
        )
        .scalars()
        .all()
    )
    analyzed = max((r.analyzed_at for r in rows), default=None)
    return {
        "analyzed_at": analyzed.isoformat() if analyzed else None,
        "terms": [
            {
                "term": r.term,
                "mention_count": r.mention_count,
                "sample_channels": r.sample_channels or [],
                "dropi_candidates": r.dropi_candidates or [],
            }
            for r in rows
        ],
    }
