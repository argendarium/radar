"""Configuración central. Todo sale de variables de entorno (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    """Como os.getenv, pero una variable vacía en .env usa el valor por defecto."""
    return os.getenv(name) or default


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in _env(name, default).split(",") if x.strip()]


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str = _env("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'radar.db'}")

    # Apify
    apify_token: str = _env("APIFY_TOKEN", "")
    meta_actor_id: str = _env("META_ACTOR_ID", "apify/facebook-ads-scraper")
    meta_countries: list[str] = field(default_factory=lambda: _list("META_COUNTRIES", "DO,MX,CO"))
    meta_keywords: list[str] = field(
        default_factory=lambda: _list("META_KEYWORDS", "pago contra entrega,envio gratis,paga al recibir")
    )
    meta_results_limit: int = _int("META_RESULTS_LIMIT", 100)
    tiktok_actor_id: str = _env("TIKTOK_ACTOR_ID", "")
    tiktok_input_file: Path = ROOT / "config" / "tiktok_input.json"
    apify_max_charge_usd: float = _float("APIFY_MAX_CHARGE_USD", 2.0)

    # Claude
    anthropic_api_key: str = _env("ANTHROPIC_API_KEY", "")
    claude_model: str = _env("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    max_normalize_per_run: int = _int("MAX_NORMALIZE_PER_RUN", 40)

    # Negocio
    usd_to_dop: float = _float("USD_TO_DOP", 60.0)  # Actualizar a la tasa real

    # Pesos del score (deben sumar 1.0)
    w_longevity: float = _float("W_LONGEVITY", 0.35)
    w_copies: float = _float("W_COPIES", 0.25)
    w_intensity: float = _float("W_INTENSITY", 0.20)
    w_viability: float = _float("W_VIABILITY", 0.20)

    # Alertas
    telegram_bot_token: str = _env("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = _env("TELEGRAM_CHAT_ID", "")


settings = Settings()
