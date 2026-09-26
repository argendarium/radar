"""Extrae identificadores de producto desde links que el operador pega a mano."""
from __future__ import annotations

import re
from urllib.parse import urlparse


class UrlError(ValueError):
    pass


def detect_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    labels = host.split(".")
    if "amazon" in labels:
        return "amazon"
    if "aliexpress" in labels:
        return "aliexpress"
    if "alibaba" in labels:
        return "alibaba"
    raise UrlError(f"No reconozco el sitio de este link: {url}")


def extract_amazon_asin(url: str) -> str:
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    if not match:
        raise UrlError("No encontré un ASIN válido en el link de Amazon (busco /dp/ASIN o /gp/product/ASIN)")
    return match.group(1)


def extract_aliexpress_product_id(url: str) -> str:
    match = re.search(r"/item/(?:[^/]*?)?(\d+)\.html", url) or re.search(r"[?&]productId=(\d+)", url)
    if not match:
        raise UrlError("No encontré un ID de producto válido en el link de AliExpress (busco /item/<id>.html)")
    return match.group(1)
