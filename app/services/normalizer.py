"""Normalización con Claude: anuncio crudo -> producto agrupado y evaluado.

Claude mira la miniatura y el texto, decide si es un producto físico,
le pone un nombre normalizado (para agrupar copias entre anunciantes)
y evalúa viabilidad para contra entrega en RD.
"""
from __future__ import annotations

import json
import re

from sqlalchemy import select

from app.config import settings
from app.db import Ad, Product, session_scope, utcnow
from app.mapping import slugify

SYSTEM = """Eres analista de e-commerce contra entrega (COD) en República Dominicana.
Recibes un anuncio (imagen y/o texto). Responde SOLO un objeto JSON válido, sin texto extra ni backticks.

Esquema:
{
  "es_producto_fisico": boolean,
  "nombre": "nombre genérico corto en español, sin marca (ej: 'corrector de postura')",
  "categoria": "hogar | belleza | salud y bienestar | cocina | mascotas | autos | tecnologia | fitness | bebes | herramientas | otro",
  "problema": "problema que resuelve, una frase",
  "wow": 0-10,
  "tiene_tallas": boolean,
  "fragil": boolean,
  "peso": "ligero | medio | pesado",
  "precio_detectado": number o null,
  "moneda": "DOP | MXN | COP | USD | null",
  "viabilidad": 0-10,
  "angulo": "ángulo de venta principal para RD, una frase",
  "hooks": ["3 hooks de máximo 8 palabras para video de 5 segundos"]
}

Criterios de viabilidad: margen potencial 3x+, efecto wow en video, resuelve problema claro,
difícil de conseguir en tiendas locales, ligero y no frágil, sin tallas, precio de impulso
RD$1,500-3,500, bajo riesgo de competir con Temu/Shein en precio.
Si es un servicio, curso, app, marca de ropa con tallas o no se identifica un producto: es_producto_fisico=false.
Si el producto coincide con uno de la lista de nombres existentes, usa EXACTAMENTE ese nombre."""


class NormalizerError(RuntimeError):
    pass


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Respuesta sin JSON")
    return json.loads(match.group(0))


def _ask_claude(client, ad: Ad, existing_names: list[str], with_image: bool) -> dict:
    content: list[dict] = []
    if with_image and ad.image_url:
        content.append({"type": "image", "source": {"type": "url", "url": ad.image_url}})
    content.append({
        "type": "text",
        "text": (
            f"País del anuncio: {ad.country or 'desconocido'}\n"
            f"Anunciante: {ad.advertiser or 'desconocido'}\n"
            f"Landing: {ad.landing_url or 'n/d'}\n"
            f"Texto del anuncio:\n{(ad.text or '')[:1500]}\n\n"
            f"Nombres de productos existentes: {', '.join(existing_names[:150]) or 'ninguno'}"
        ),
    })
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=800,
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    return _parse_json(text)


def _merge_product(product: Product, data: dict) -> None:
    def set_if_empty(attr: str, value):
        if value not in (None, "", []) and getattr(product, attr) in (None, "", []):
            setattr(product, attr, value)

    set_if_empty("category", data.get("categoria"))
    set_if_empty("problem", data.get("problema"))
    set_if_empty("angle", data.get("angulo"))
    set_if_empty("hooks", data.get("hooks"))
    set_if_empty("weight", data.get("peso"))
    set_if_empty("price_detected", data.get("precio_detectado"))
    set_if_empty("price_currency", data.get("moneda"))
    if product.has_sizes is None:
        product.has_sizes = bool(data.get("tiene_tallas"))
    if product.fragile is None:
        product.fragile = bool(data.get("fragil"))

    for attr, key in (("viability_ai", "viabilidad"), ("wow", "wow")):
        new = data.get(key)
        if isinstance(new, (int, float)):
            old = getattr(product, attr)
            value = float(new) if old is None else (float(old) + float(new)) / 2  # promedio simple
            setattr(product, attr, round(value, 1) if attr == "viability_ai" else int(round(value)))


def normalize(limit: int | None = None) -> int:
    if not settings.anthropic_api_key:
        raise NormalizerError("Falta ANTHROPIC_API_KEY en .env")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    limit = limit or settings.max_normalize_per_run
    processed = 0

    with session_scope() as session:
        ads = session.scalars(
            select(Ad).where(Ad.normalized_at.is_(None), Ad.source != "demo")
            .order_by(Ad.last_seen.desc()).limit(limit)
        ).all()
        existing_names = list(session.scalars(select(Product.name).order_by(Product.score.desc())).all())

        for ad in ads:
            try:
                try:
                    data = _ask_claude(client, ad, existing_names, with_image=True)
                except anthropic.BadRequestError:
                    data = _ask_claude(client, ad, existing_names, with_image=False)  # imagen caducada o inválida
            except (anthropic.APIError, ValueError, json.JSONDecodeError) as exc:
                print(f"[normalizer] anuncio {ad.id} omitido: {exc}")
                continue

            ad.normalized_at = utcnow()
            ad.is_product = bool(data.get("es_producto_fisico"))
            if ad.is_product and data.get("nombre"):
                name = str(data["nombre"]).strip().lower()
                slug = slugify(name)
                product = session.scalar(select(Product).where(Product.slug == slug))
                if product is None:
                    product = Product(slug=slug, name=name)
                    session.add(product)
                    existing_names.append(name)
                _merge_product(product, data)
                ad.product = product
            session.flush()
            processed += 1
    return processed
