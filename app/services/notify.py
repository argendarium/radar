"""Alerta diaria con el top 3 por Telegram (opcional)."""
from __future__ import annotations

import httpx
from sqlalchemy import select

from app.config import settings
from app.db import Product, session_scope


def top_products(limit: int = 3) -> list[Product]:
    with session_scope() as session:
        return list(session.scalars(
            select(Product).where(Product.status == "candidato").order_by(Product.score.desc()).limit(limit)
        ).all())


def build_message(products: list[Product]) -> str:
    if not products:
        return "Radar: no hay candidatos nuevos hoy."
    lines = ["Radar: top candidatos de hoy", ""]
    for i, p in enumerate(products, 1):
        lines.append(f"{i}. {p.name.capitalize()} | score {p.score:.1f}")
        if p.angle:
            lines.append(f"   Ángulo: {p.angle}")
    return "\n".join(lines)


def send_top() -> str:
    message = build_message(top_products())
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return f"Telegram no configurado. Mensaje:\n{message}"
    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": settings.telegram_chat_id, "text": message},
        timeout=20,
    )
    response.raise_for_status()
    return "Enviado a Telegram"
