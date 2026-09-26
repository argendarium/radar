"""Piezas compartidas por los colectores."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Ad, utcnow


class CollectorError(RuntimeError):
    pass


@dataclass
class AdRecord:
    source: str
    external_id: str
    country: str | None = None
    advertiser: str | None = None
    text: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    landing_url: str | None = None
    likes: int | None = None
    comments: int | None = None
    started_at: datetime | None = None
    is_active: bool = True
    raw: dict | None = None


def _attr(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def run_actor(actor_id: str, run_input: dict, max_items: int | None = None,
              max_charge_usd: float | None = None, run_timeout_secs: int | None = None) -> Iterator[dict]:
    """Ejecuta un actor de Apify, espera a que termine y devuelve sus items."""
    if not settings.apify_token:
        raise CollectorError("Falta APIFY_TOKEN en .env")
    from apify_client import ApifyClient

    client = ApifyClient(settings.apify_token)
    charge = max_charge_usd if max_charge_usd is not None else settings.apify_max_charge_usd
    run = client.actor(actor_id).call(
        run_input=run_input,
        max_items=max_items,
        max_total_charge_usd=Decimal(str(charge)),
        run_timeout=timedelta(seconds=run_timeout_secs) if run_timeout_secs is not None else None,
    )
    if run is None:
        raise CollectorError(f"El actor {actor_id} no devolvió una ejecución")
    status = str(_attr(run, "status") or "")
    dataset_id = _attr(run, "default_dataset_id", "defaultDatasetId")
    if "SUCCEEDED" not in status.upper():
        raise CollectorError(f"El actor {actor_id} terminó con estado {status}")
    yield from client.dataset(dataset_id).iterate_items(clean=True)


def upsert_ads(session: Session, records: list[AdRecord]) -> int:
    """Inserta anuncios nuevos y refresca los existentes (mantiene first_seen)."""
    now = utcnow()
    count = 0
    for rec in records:
        if not rec.external_id:
            continue
        ad = session.scalar(select(Ad).where(Ad.source == rec.source, Ad.external_id == rec.external_id))
        if ad is None:
            ad = Ad(source=rec.source, external_id=rec.external_id, first_seen=now)
            session.add(ad)
        if rec.country:
            countries = [c for c in (ad.country or "").split(",") if c]
            if rec.country.upper() not in countries:
                countries.append(rec.country.upper())
            ad.country = ",".join(countries)
        for field in ("advertiser", "text", "image_url", "video_url", "landing_url",
                      "likes", "comments", "started_at", "raw"):
            value = getattr(rec, field)
            if value is not None:
                setattr(ad, field, value)
        ad.is_active = rec.is_active
        ad.last_seen = now
        count += 1
    session.flush()
    return count
