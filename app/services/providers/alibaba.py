"""Costo de sourcing en Alibaba vía un actor de Apify de una sola URL.

IMPORTANTE: el input y los nombres de campos dependen del actor elegido en Apify Store.
Antes de fijar ALIBABA_APIFY_ACTOR_ID, corre: python -m app.cli schema <actor_id>
y ajusta build_input() y map_item(), igual que con los colectores de Meta/TikTok.
"""
from __future__ import annotations

from app.collectors.base import CollectorError, run_actor
from app.config import settings
from app.mapping import pick, to_float, to_int


class AlibabaProviderError(RuntimeError):
    pass


def build_input(url: str) -> dict:
    return {"startUrls": [{"url": url}]}


def map_item(item: dict) -> dict:
    return {
        "price_unit": to_float(pick(item, "price", "minPrice", "price_min", "priceRange.0")),
        "moq": to_int(pick(item, "moq", "minOrder", "min_order_quantity")),
        "supplier_name": pick(item, "supplierName", "companyName", "seller", "storeName"),
        "raw": item,
    }


def fetch_sourcing_signal(url: str) -> dict:
    if not settings.alibaba_apify_actor_id:
        raise AlibabaProviderError("Falta ALIBABA_APIFY_ACTOR_ID en .env")
    try:
        items = list(run_actor(settings.alibaba_apify_actor_id, build_input(url), max_items=1,
                               max_charge_usd=settings.alibaba_max_charge_usd, run_timeout_secs=45))
    except CollectorError as exc:
        raise AlibabaProviderError(str(exc)) from exc
    except Exception as exc:
        raise AlibabaProviderError(f"Error al consultar Alibaba: {exc}") from exc
    if not items:
        raise AlibabaProviderError("Alibaba no devolvió datos para ese link")
    return map_item(items[0])
