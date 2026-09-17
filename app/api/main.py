"""API del radar. Sirve el dashboard en / y la API en /api."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.config import ROOT, settings
from app.db import STATUSES, Ad, Product, Run, init_db, session_scope
from app.jobs import JOBS, execute, start_run
from app.services import scorer

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Radar de productos ganadores", version="0.1.0", lifespan=lifespan)
DASHBOARD = ROOT / "dashboard" / "index.html"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def product_summary(p: Product) -> dict:
    signals = scorer.compute(scorer.signals_for(p), p.viability_ai, p.supplier_cost_usd, p.sale_price_dop,
                             p.has_sizes, p.fragile, p.weight)
    thumb = next((a.image_url for a in p.ads if a.image_url), None)
    return {
        "id": p.id, "name": p.name, "category": p.category, "status": p.status, "is_demo": p.is_demo,
        "score": p.score, "s_longevity": p.s_longevity, "s_copies": p.s_copies,
        "s_intensity": p.s_intensity, "s_viability": p.s_viability,
        "days_active": signals["days_active"], "advertisers": signals["advertisers"],
        "ads_count": len(p.ads),
        "countries": sorted({c for a in p.ads if a.country for c in a.country.split(",")}),
        "margin_ratio": signals["margin_ratio"], "penalty": signals["penalty"], "thumbnail": thumb, "updated_at": _iso(p.updated_at),
    }


def product_detail(p: Product) -> dict:
    data = product_summary(p)
    data.update({
        "problem": p.problem, "angle": p.angle, "hooks": p.hooks or [], "wow": p.wow,
        "has_sizes": p.has_sizes, "fragile": p.fragile, "weight": p.weight,
        "viability_ai": p.viability_ai, "price_detected": p.price_detected, "price_currency": p.price_currency,
        "supplier_cost_usd": p.supplier_cost_usd, "sale_price_dop": p.sale_price_dop, "notes": p.notes,
        "usd_to_dop": settings.usd_to_dop,
        "ads": [
            {"id": a.id, "source": a.source, "country": a.country, "advertiser": a.advertiser, "text": a.text,
             "image_url": a.image_url, "video_url": a.video_url, "landing_url": a.landing_url,
             "likes": a.likes, "comments": a.comments, "started_at": _iso(a.started_at),
             "last_seen": _iso(a.last_seen), "is_active": a.is_active}
            for a in sorted(p.ads, key=lambda a: a.started_at or a.first_seen)
        ],
    })
    return data


class ProductUpdate(BaseModel):
    status: str | None = None
    supplier_cost_usd: float | None = Field(default=None, ge=0)
    sale_price_dop: float | None = Field(default=None, ge=0)
    notes: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "apify": bool(settings.apify_token),
        "claude": bool(settings.anthropic_api_key),
        "tiktok": bool(settings.tiktok_actor_id),
        "telegram": bool(settings.telegram_bot_token and settings.telegram_chat_id),
    }


@app.get("/api/stats")
def stats() -> dict:
    with session_scope() as s:
        by_status = dict(s.execute(select(Product.status, func.count()).group_by(Product.status)).all())
        return {
            "ads": s.scalar(select(func.count()).select_from(Ad)) or 0,
            "pending_normalize": s.scalar(
                select(func.count()).select_from(Ad).where(Ad.normalized_at.is_(None), Ad.source != "demo")) or 0,
            "products": sum(by_status.values()),
            "by_status": {k: by_status.get(k, 0) for k in STATUSES},
        }


@app.get("/api/products")
def list_products(
    status: str | None = None,
    country: str | None = None,
    q: str | None = None,
    limit: int = Query(100, le=500),
) -> list[dict]:
    with session_scope() as s:
        stmt = select(Product).options(selectinload(Product.ads)).order_by(Product.score.desc())
        if status:
            stmt = stmt.where(Product.status == status)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(Product.name).like(like), func.lower(Product.category).like(like)))
        if country:
            stmt = stmt.where(Product.ads.any(Ad.country.like(f"%{country.upper()[:2]}%")))
        return [product_summary(p) for p in s.scalars(stmt.limit(limit)).all()]


@app.get("/api/products/{product_id}")
def get_product(product_id: int) -> dict:
    with session_scope() as s:
        p = s.scalar(select(Product).options(selectinload(Product.ads)).where(Product.id == product_id))
        if not p:
            raise HTTPException(404, "Producto no encontrado")
        return product_detail(p)


@app.patch("/api/products/{product_id}")
def update_product(product_id: int, payload: ProductUpdate) -> dict:
    with session_scope() as s:
        p = s.scalar(select(Product).options(selectinload(Product.ads)).where(Product.id == product_id))
        if not p:
            raise HTTPException(404, "Producto no encontrado")
        changes = payload.model_dump(exclude_unset=True)
        if "status" in changes and changes["status"] not in STATUSES:
            raise HTTPException(422, f"Estado inválido. Usa: {', '.join(STATUSES)}")
        for key, value in changes.items():
            setattr(p, key, value)
        scorer.apply(p)
        s.flush()
        return product_detail(p)


@app.post("/api/jobs/{kind}", status_code=202)
def run_job(kind: str, background: BackgroundTasks) -> dict:
    if kind not in JOBS:
        raise HTTPException(404, f"Trabajo desconocido. Usa: {', '.join(JOBS)}")
    run_id = start_run(kind)
    background.add_task(execute, kind, run_id)
    return {"id": run_id, "kind": kind, "status": "running"}


@app.get("/api/runs")
def list_runs(limit: int = Query(10, le=100)) -> list[dict]:
    with session_scope() as s:
        runs = s.scalars(select(Run).order_by(Run.id.desc()).limit(limit)).all()
        return [
            {"id": r.id, "kind": r.kind, "status": r.status, "message": r.message, "items": r.items,
             "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at)}
            for r in runs
        ]


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD)
