"""Agregación de ventas para el dashboard admin (feature 012, research R3)."""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

import structlog

from app.clients.woocommerce import get_wc_client
from app.core.cache import cache_get, cache_set
from app.services.admin.products_admin import list_products, supplier_cost_map

logger = structlog.get_logger()

_CACHE_TTL = 60
_EXCLUDED_STATUSES = {"cancelled", "refunded", "failed", "trash", "checkout-draft"}

PERIODS = {"today": 1, "7d": 7, "30d": 30}


def _period_start(period: str) -> str:
    days = PERIODS[period]
    now = datetime.now(UTC)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=days)
    return start.isoformat()


async def _fetch_period_orders(period: str) -> list[dict]:
    wc = await get_wc_client()
    after = _period_start(period)
    orders: list[dict] = []
    page = 1
    while True:
        batch, total = await wc.list_orders(after=after, page=page, per_page=100, status="any")
        orders.extend(batch)
        if len(orders) >= total or not batch:
            break
        page += 1
    return orders


async def get_stats(period: str) -> dict:
    cache_key = f"admin:stats:{period}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    orders = await _fetch_period_orders(period)
    cost_map = supplier_cost_map(await list_products())

    revenue = 0.0
    profit = 0.0
    by_status: Counter = Counter()
    by_payment: Counter = Counter()
    product_units: Counter = Counter()
    product_revenue: defaultdict = defaultdict(float)
    product_names: dict = {}
    counted_orders = 0

    for o in orders:
        status = o.get("status", "")
        by_status[status] += 1
        if status in _EXCLUDED_STATUSES:
            continue

        counted_orders += 1
        total = float(o.get("total") or 0)
        revenue += total
        method = o.get("payment_method") or "other"
        by_payment["cod" if method == "cod" else "other"] += 1

        for item in o.get("line_items", []):
            pid = item.get("product_id")
            qty = int(item.get("quantity") or 0)
            line_total = float(item.get("total") or 0)
            product_units[pid] += qty
            product_revenue[pid] += line_total
            product_names[pid] = item.get("name", "")
            cost = cost_map.get(pid)
            profit += line_total - (cost * qty if cost is not None else 0)

    top = [
        {
            "product_id": pid,
            "name": product_names.get(pid, ""),
            "units": units,
            "revenue": round(product_revenue[pid]),
        }
        for pid, units in product_units.most_common(5)
    ]

    result = {
        "period": period,
        "revenue": round(revenue),
        "orders": counted_orders,
        "avg_ticket": round(revenue / counted_orders) if counted_orders else 0,
        "by_status": dict(by_status),
        "by_payment": dict(by_payment),
        "estimated_profit": round(profit),
        "top_products": top,
    }
    await cache_set(cache_key, result, _CACHE_TTL)
    return result
