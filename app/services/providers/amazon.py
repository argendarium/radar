"""Señal de demanda en Amazon vía RapidAPI 'Real-Time Amazon Data' (tier gratis: 100 requests/mes)."""
from __future__ import annotations

import httpx

from app.config import settings
from app.mapping import to_float, to_int
from app.services.providers.urls import extract_amazon_asin

RAPIDAPI_HOST = "real-time-amazon-data.p.rapidapi.com"


class AmazonProviderError(RuntimeError):
    pass


def fetch_amazon_signal(url: str) -> dict:
    if not settings.rapidapi_key:
        raise AmazonProviderError("Falta RAPIDAPI_KEY en .env")
    asin = extract_amazon_asin(url)
    try:
        resp = httpx.get(
            f"https://{RAPIDAPI_HOST}/product-details",
            params={"asin": asin, "country": "US"},
            headers={"x-rapidapi-key": settings.rapidapi_key, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise AmazonProviderError(f"No se pudo conectar con Amazon: {exc}") from exc
    if resp.status_code == 429:
        raise AmazonProviderError("Límite mensual de Amazon alcanzado (tier gratis de RapidAPI)")
    if resp.status_code != 200:
        raise AmazonProviderError(f"Amazon respondió {resp.status_code}")
    data = (resp.json() or {}).get("data") or {}
    if not data:
        raise AmazonProviderError("Amazon no encontró ese producto")
    return {
        "price": to_float(data.get("product_price")),
        "rating": to_float(data.get("product_star_rating")),
        "reviews_count": to_int(data.get("product_num_ratings")),
        "bought_last_month": data.get("sales_volume"),
        "raw": data,
    }
