"""Registro y agregación del consumo del LLM (feature 013, research R1/R2)."""

import json
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select

from app.config import settings

logger = structlog.get_logger()

PERIODS = {"today": 1, "7d": 7, "30d": 30}


def _prices() -> dict[str, tuple[float, float]]:
    try:
        raw = json.loads(settings.AI_MODEL_PRICES)
        return {k: (float(v[0]), float(v[1])) for k, v in raw.items()}
    except (ValueError, TypeError, IndexError):
        logger.warning("ai_usage.bad_prices_config")
        return {}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """USD según tabla de precios; None si el modelo no está (→ 'no estimado')."""
    for prefix, (p_in, p_out) in _prices().items():
        if model.startswith(prefix):
            return prompt_tokens / 1e6 * p_in + completion_tokens / 1e6 * p_out
    return None


async def record_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    session_id: str | None = None,
    channel: str | None = None,
) -> None:
    """Persistencia best-effort — jamás propaga errores (no romper respuestas del bot)."""
    try:
        from app.db.base import AsyncSessionLocal
        from app.models.ai_usage import AiUsage

        async with AsyncSessionLocal() as db:
            db.add(
                AiUsage(
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
                    session_id=session_id,
                    channel=channel,
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_usage.record_failed", error=str(exc))


def _period_start(period: str) -> datetime:
    now = datetime.now(UTC)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=PERIODS[period])


async def get_usage_summary(period: str) -> dict:
    from app.db.base import AsyncSessionLocal
    from app.models.ai_usage import AiUsage

    start = _period_start(period)
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(
                    AiUsage.model,
                    func.count(AiUsage.id),
                    func.coalesce(func.sum(AiUsage.prompt_tokens), 0),
                    func.coalesce(func.sum(AiUsage.completion_tokens), 0),
                    func.sum(AiUsage.cost_usd),
                    func.count(AiUsage.id).filter(AiUsage.cost_usd.is_(None)),
                )
                .where(AiUsage.created_at >= start)
                .group_by(AiUsage.model)
            )
        ).all()

        # nº de sesiones distintas con uso en el período ≈ conversaciones
        conversations = (
            await db.execute(
                select(func.count(func.distinct(AiUsage.session_id))).where(
                    AiUsage.created_at >= start, AiUsage.session_id.isnot(None)
                )
            )
        ).scalar() or 0

    by_model = []
    total_prompt = total_completion = unestimated = 0
    total_cost = 0.0
    for model, calls, p_tok, c_tok, cost, no_price in rows:
        total_prompt += int(p_tok)
        total_completion += int(c_tok)
        unestimated += int(no_price)
        cost_f = float(cost) if cost is not None else 0.0
        total_cost += cost_f
        by_model.append(
            {
                "model": model,
                "calls": int(calls),
                "tokens": int(p_tok) + int(c_tok),
                "cost_usd": round(cost_f, 4),
            }
        )
    by_model.sort(key=lambda m: m["cost_usd"], reverse=True)

    return {
        "period": period,
        "total_tokens": total_prompt + total_completion,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "cost_usd": round(total_cost, 4),
        "unestimated_calls": unestimated,
        "by_model": by_model,
        "conversations": conversations,
        "avg_cost_per_conversation": round(total_cost / conversations, 4) if conversations else 0,
    }
