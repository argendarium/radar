"""Orquesta el análisis on-demand de un candidato con links pegados por el operador.

Cada fuente (Amazon / AliExpress / Alibaba) es independiente: si una falla, la otra
se guarda igual. Nunca se llama automáticamente para todos los productos.
"""
from __future__ import annotations

from app.db import Product, ProductEnrichment, utcnow
from app.services.providers import alibaba, aliexpress, amazon
from app.services.providers.urls import UrlError, detect_source


def _result(status: str, **extra) -> dict:
    return {"status": status, **extra}


def _fetch_amazon(url: str | None) -> dict:
    if not url:
        return _result("skipped")
    try:
        signal = amazon.fetch_amazon_signal(url)
    except (UrlError, amazon.AmazonProviderError) as exc:
        return _result("error", message=str(exc))
    return _result("ok", **signal)


def _fetch_sourcing(url: str | None) -> dict:
    if not url:
        return _result("skipped")
    try:
        source = detect_source(url)
    except UrlError as exc:
        return _result("error", message=str(exc))
    if source == "amazon":
        return _result("error", source=source,
                       message="Pega un link de AliExpress o Alibaba, no de Amazon, en el campo de sourcing")
    fetcher = aliexpress.fetch_sourcing_signal if source == "aliexpress" else alibaba.fetch_sourcing_signal
    try:
        signal = fetcher(url)
    except (UrlError, aliexpress.AliexpressProviderError, alibaba.AlibabaProviderError) as exc:
        return _result("error", source=source, message=str(exc))
    return _result("ok", source=source, **signal)


def analyze(product: Product, amazon_url: str | None, sourcing_url: str | None) -> dict:
    if not amazon_url and not sourcing_url:
        raise ValueError("Pega al menos un link para analizar")
    amazon_result = _fetch_amazon(amazon_url)
    sourcing_result = _fetch_sourcing(sourcing_url)

    if amazon_result["status"] == "ok" or sourcing_result["status"] == "ok" or product.enrichment is not None:
        enrichment = product.enrichment or ProductEnrichment(product_id=product.id)
        now = utcnow()
        if amazon_result["status"] == "ok":
            enrichment.amazon_url = amazon_url
            enrichment.amazon_price = amazon_result.get("price")
            enrichment.amazon_rating = amazon_result.get("rating")
            enrichment.amazon_reviews_count = amazon_result.get("reviews_count")
            enrichment.amazon_bought_last_month = amazon_result.get("bought_last_month")
            enrichment.raw_amazon = amazon_result.get("raw")
            enrichment.amazon_fetched_at = now
        if sourcing_result["status"] == "ok":
            enrichment.sourcing_source = sourcing_result.get("source")
            enrichment.sourcing_url = sourcing_url
            enrichment.sourcing_price_unit = sourcing_result.get("price_unit")
            enrichment.sourcing_moq = sourcing_result.get("moq")
            enrichment.sourcing_supplier_name = sourcing_result.get("supplier_name")
            enrichment.raw_sourcing = sourcing_result.get("raw")
            enrichment.sourcing_fetched_at = now
        product.enrichment = enrichment

    return {
        "amazon": {k: v for k, v in amazon_result.items() if k != "raw"},
        "sourcing": {k: v for k, v in sourcing_result.items() if k != "raw"},
    }
