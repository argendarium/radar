"""Scoring de productos ganadores.

score = 0.35*longevidad + 0.25*copias + 0.20*intensidad + 0.20*viabilidad   (cada señal 0-10)

- longevidad: días máximos que un anuncio del producto lleva activo (30+ días = 10)
- copias:     anunciantes distintos vendiendo el mismo producto (5+ = 10)
- intensidad: volumen de anuncios activos y engagement (TikTok)
- viabilidad: evaluación de Claude, ajustada por margen real si ya cargaste costo y precio

Penalizaciones multiplicativas (en contra entrega disparan devoluciones o costos):
tallas x0.6, frágil x0.8, pesado x0.85
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import Product, session_scope


@dataclass
class AdSignal:
    advertiser: str | None
    started_at: datetime | None
    first_seen: datetime
    last_seen: datetime
    is_active: bool
    likes: int | None = None
    comments: int | None = None


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def longevity_score(ads: list[AdSignal]) -> tuple[float, int]:
    if not ads:
        return 0.0, 0
    days = max(((a.last_seen - (a.started_at or a.first_seen)).days for a in ads), default=0)
    days = max(days, 0)
    return round(_clamp(days / 30 * 10), 2), days


def copies_score(ads: list[AdSignal]) -> tuple[float, int]:
    advertisers = {(a.advertiser or "").strip().lower() for a in ads if a.advertiser}
    n = len(advertisers)
    return (round(_clamp((n - 1) / 4 * 10), 2) if n else 0.0), n


def intensity_score(ads: list[AdSignal]) -> float:
    active = sum(1 for a in ads if a.is_active)
    volume = _clamp(math.log1p(active) / math.log1p(20) * 10)
    engagement_values = [(a.likes or 0) + 5 * (a.comments or 0) for a in ads if a.likes or a.comments]
    if not engagement_values:
        return round(volume, 2)
    engagement = _clamp(math.log1p(sum(engagement_values)) / math.log1p(200_000) * 10)
    return round((volume + engagement) / 2, 2)


def margin_ratio(cost_usd: float | None, sale_price_dop: float | None, fx: float) -> float | None:
    if not cost_usd or not sale_price_dop or cost_usd <= 0:
        return None
    return sale_price_dop / (cost_usd * fx)


def viability_score(viability_ai: float | None, ratio: float | None) -> float:
    base = viability_ai if viability_ai is not None else 5.0
    if ratio is None:
        return round(_clamp(base), 2)
    margin = _clamp((ratio - 1.5) / (4.0 - 1.5) * 10)  # 1.5x = 0, 4x+ = 10
    return round(_clamp(0.5 * base + 0.5 * margin), 2)


PENALTIES = {"has_sizes": 0.6, "fragile": 0.8, "heavy": 0.85}


def penalty_multiplier(has_sizes: bool | None, fragile: bool | None, weight: str | None) -> float:
    multiplier = 1.0
    if has_sizes:
        multiplier *= PENALTIES["has_sizes"]
    if fragile:
        multiplier *= PENALTIES["fragile"]
    if (weight or "").lower() == "pesado":
        multiplier *= PENALTIES["heavy"]
    return multiplier


def compute(ads: list[AdSignal], viability_ai: float | None, cost_usd: float | None,
            sale_price_dop: float | None, has_sizes: bool | None = None, fragile: bool | None = None,
            weight: str | None = None) -> dict:
    s_long, days = longevity_score(ads)
    s_copies, advertisers = copies_score(ads)
    s_int = intensity_score(ads)
    ratio = margin_ratio(cost_usd, sale_price_dop, settings.usd_to_dop)
    s_via = viability_score(viability_ai, ratio)
    penalty = penalty_multiplier(has_sizes, fragile, weight)
    score = (settings.w_longevity * s_long + settings.w_copies * s_copies
             + settings.w_intensity * s_int + settings.w_viability * s_via) * penalty
    return {
        "score": round(score, 2), "s_longevity": s_long, "s_copies": s_copies,
        "s_intensity": s_int, "s_viability": s_via,
        "days_active": days, "advertisers": advertisers,
        "margin_ratio": round(ratio, 2) if ratio else None, "penalty": round(penalty, 2),
    }


def signals_for(product: Product) -> list[AdSignal]:
    return [
        AdSignal(a.advertiser, a.started_at, a.first_seen, a.last_seen, a.is_active, a.likes, a.comments)
        for a in product.ads
    ]


def apply(product: Product) -> dict:
    result = compute(signals_for(product), product.viability_ai, product.supplier_cost_usd,
                     product.sale_price_dop, product.has_sizes, product.fragile, product.weight)
    for key in ("score", "s_longevity", "s_copies", "s_intensity", "s_viability"):
        setattr(product, key, result[key])
    return result


def score_all() -> int:
    with session_scope() as session:
        products = session.scalars(select(Product).options(selectinload(Product.ads))).all()
        for product in products:
            apply(product)
        return len(products)
