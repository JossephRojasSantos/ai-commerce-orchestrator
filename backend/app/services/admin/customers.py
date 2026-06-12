"""Clientes derivados de las órdenes, agregados por teléfono (feature 012, research R4)."""

import re

from app.clients.woocommerce import get_wc_client
from app.core.cache import cache_get, cache_set

_CACHE_KEY = "admin:customers"
_CACHE_TTL = 120
_EXCLUDED_STATUSES = {"cancelled", "refunded", "failed", "trash", "checkout-draft"}


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D+", "", raw or "")
    if digits.startswith("57") and len(digits) == 12:
        digits = digits[2:]
    return digits


async def _fetch_all_orders() -> list[dict]:
    wc = await get_wc_client()
    orders: list[dict] = []
    page = 1
    while True:
        batch, total = await wc.list_orders(page=page, per_page=100, status="any")
        orders.extend(batch)
        if len(orders) >= total or not batch:
            break
        page += 1
    return orders


async def list_customers(search: str = "") -> list[dict]:
    cached = await cache_get(_CACHE_KEY)
    if cached is None:
        orders = await _fetch_all_orders()
        agg: dict[str, dict] = {}

        # orders viene desc por fecha: el primero visto es el más reciente
        for o in orders:
            billing = o.get("billing", {})
            phone = normalize_phone(billing.get("phone", ""))
            if not phone:
                continue

            entry = agg.setdefault(
                phone,
                {
                    "phone": phone,
                    "name": f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip(),
                    "city": billing.get("city", ""),
                    "orders_count": 0,
                    "total_spent": 0.0,
                    "last_order_date": o.get("date_created", ""),
                    "orders": [],
                },
            )
            if o.get("status") in _EXCLUDED_STATUSES:
                continue
            entry["orders_count"] += 1
            entry["total_spent"] += float(o.get("total") or 0)
            entry["orders"].append(
                {
                    "id": o.get("id"),
                    "date": o.get("date_created", ""),
                    "total": float(o.get("total") or 0),
                    "status": o.get("status", ""),
                }
            )

        cached = sorted(
            (e for e in agg.values() if e["orders_count"] > 0),
            key=lambda e: e["last_order_date"],
            reverse=True,
        )
        for e in cached:
            e["total_spent"] = round(e["total_spent"])
        await cache_set(_CACHE_KEY, cached, _CACHE_TTL)

    if search:
        s = search.lower()
        return [c for c in cached if s in c["phone"] or s in c["name"].lower()]
    return cached
