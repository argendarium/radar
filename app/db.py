"""Modelos y sesión. SQLite hoy; cambia DATABASE_URL a Postgres sin tocar código."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings

if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


STATUSES = ("candidato", "en_prueba", "ganador", "descartado")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(120))
    problem: Mapped[str | None] = mapped_column(Text)
    angle: Mapped[str | None] = mapped_column(Text)
    hooks: Mapped[list | None] = mapped_column(JSON)
    wow: Mapped[int | None] = mapped_column(Integer)
    has_sizes: Mapped[bool | None] = mapped_column(Boolean)
    fragile: Mapped[bool | None] = mapped_column(Boolean)
    weight: Mapped[str | None] = mapped_column(String(20))
    viability_ai: Mapped[float | None] = mapped_column(Float)
    price_detected: Mapped[float | None] = mapped_column(Float)
    price_currency: Mapped[str | None] = mapped_column(String(8))

    supplier_cost_usd: Mapped[float | None] = mapped_column(Float)
    sale_price_dop: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="candidato", index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    s_longevity: Mapped[float] = mapped_column(Float, default=0.0)
    s_copies: Mapped[float] = mapped_column(Float, default=0.0)
    s_intensity: Mapped[float] = mapped_column(Float, default=0.0)
    s_viability: Mapped[float] = mapped_column(Float, default=0.0)

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    ads: Mapped[list["Ad"]] = relationship(back_populates="product")


class Ad(Base):
    __tablename__ = "ads"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_ad_source_ext"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)  # meta | tiktok | demo
    external_id: Mapped[str] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(60), index=True)  # "DO,MX" si aparece en varios
    advertiser: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(Text)
    landing_url: Mapped[str | None] = mapped_column(Text)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    raw: Mapped[dict | None] = mapped_column(JSON)

    is_product: Mapped[bool | None] = mapped_column(Boolean)
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    product: Mapped[Product | None] = relationship(back_populates="ads")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | error
    message: Mapped[str | None] = mapped_column(Text)
    items: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
