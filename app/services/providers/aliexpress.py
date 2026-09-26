"""Costo de sourcing en AliExpress vía la API oficial de afiliados (gratis).

Aprobación de la llave en portals.aliexpress.com > Tools > Dropshipping and Affiliates developer API.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.mapping import to_float
from app.services.providers.urls import UrlError, extract_aliexpress_product_id

ALIEXPRESS_GATEWAY = "http://gw.api.taobao.com/router/rest"
_SHANGHAI = timezone(timedelta(hours=8))


class AliexpressProviderError(RuntimeError):
    pass


def _sign(params: dict, secret: str) -> str:
    ordered = sorted(params.items())
    base = "".join(f"{k}{v}" for k, v in ordered)
    wrapped = f"{secret}{base}{secret}"
    return hashlib.md5(wrapped.encode("utf-8")).hexdigest().upper()


def fetch_sourcing_signal(url: str) -> dict:
    if not (settings.aliexpress_app_key and settings.aliexpress_app_secret):
        raise AliexpressProviderError("Falta ALIEXPRESS_APP_KEY o ALIEXPRESS_APP_SECRET en .env")
    try:
        product_id = extract_aliexpress_product_id(url)
    except UrlError as exc:
        raise AliexpressProviderError(str(exc)) from exc
    params = {
        "app_key": settings.aliexpress_app_key,
        "method": "aliexpress.affiliate.productdetail.get",
        "sign_method": "md5",
        "timestamp": datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "product_ids": product_id,
        "target_currency": "USD",
        "target_language": "ES",
        "tracking_id": settings.aliexpress_tracking_id,
    }
    params["sign"] = _sign(params, settings.aliexpress_app_secret)
    try:
        resp = httpx.post(ALIEXPRESS_GATEWAY, data=params, timeout=20)
    except httpx.HTTPError as exc:
        raise AliexpressProviderError(f"No se pudo conectar con AliExpress: {exc}") from exc
    if resp.status_code != 200:
        raise AliexpressProviderError(f"AliExpress respondió {resp.status_code}")
    try:
        body = resp.json()
    except (ValueError, RuntimeError) as exc:
        raise AliexpressProviderError(f"AliExpress devolvió un JSON inválido: {exc}") from exc
    try:
        if "error_response" in body:
            raise AliexpressProviderError(body["error_response"].get("msg", "Error de AliExpress"))
        products = (
            body.get("aliexpress_affiliate_productdetail_get_response", {})
            .get("resp_result", {}).get("result", {}).get("products", {}).get("product", [])
        )
        if not products:
            raise AliexpressProviderError("AliExpress no encontró ese producto")
        product = products[0]
        return {
            "price_unit": to_float(product.get("target_sale_price")),
            "moq": None,  # AliExpress es venta al detalle; el MOQ real vive en Alibaba
            "supplier_name": product.get("shop_url"),
            "raw": product,
        }
    except (KeyError, AttributeError, TypeError) as exc:
        raise AliexpressProviderError(f"AliExpress devolvió una respuesta inesperada: {exc}") from exc
