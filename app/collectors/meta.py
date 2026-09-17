"""Colector de Meta Ad Library vía Apify.

La API oficial de Meta no devuelve anuncios comerciales fuera de la UE,
por eso usamos un actor de Apify sobre la biblioteca pública (sin login).

IMPORTANTE: el input y los nombres de campos dependen del actor elegido.
Antes de cambiar META_ACTOR_ID, corre:  python -m app.cli schema <actor_id>
y ajusta build_input() y map_item().
"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.collectors.base import AdRecord, run_actor, upsert_ads
from app.config import settings
from app.db import session_scope
from app.mapping import pick, to_datetime, to_int


def library_url(country: str, keyword: str) -> str:
    return (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
        f"&country={country}&media_type=all&q={quote_plus(keyword)}&search_type=keyword_unordered"
    )


def build_input(country: str) -> dict:
    """Input para apify/facebook-ads-scraper. Verificar con `cli schema` si cambias de actor."""
    return {
        "startUrls": [{"url": library_url(country, kw)} for kw in settings.meta_keywords],
        "resultsLimit": settings.meta_results_limit,
        "activeStatus": "active",
    }


def map_item(item: dict, country: str) -> AdRecord:
    external_id = pick(item, "adArchiveID", "adArchiveId", "ad_archive_id", "libraryId", "adId", "id")
    return AdRecord(
        source="meta",
        external_id=str(external_id) if external_id else "",
        country=country,
        advertiser=pick(item, "pageName", "page_name", "snapshot.page_name", "advertiser", "pageInfo.name"),
        text=pick(item, "snapshot.body.text", "snapshot.cards.0.body", "adText", "body", "text",
                  "ad_creative_bodies.0", "snapshot.title"),
        image_url=pick(item, "snapshot.images.0.originalImageUrl", "snapshot.images.0.resizedImageUrl",
                       "snapshot.videos.0.videoPreviewImageUrl", "snapshot.cards.0.originalImageUrl",
                       "snapshot.cards.0.resizedImageUrl", "imageUrl", "thumbnailUrl", "creativeImageUrls.0"),
        video_url=pick(item, "snapshot.videos.0.videoHdUrl", "snapshot.videos.0.videoSdUrl", "videoUrl",
                       "creativeVideoUrls.0"),
        landing_url=pick(item, "snapshot.linkUrl", "snapshot.cards.0.linkUrl", "linkUrl", "landingPageUrl"),
        likes=to_int(pick(item, "likes", "reactions")),
        comments=to_int(pick(item, "comments")),
        started_at=to_datetime(pick(item, "startDate", "start_date", "startDateFormatted",
                                    "ad_delivery_start_time", "startedRunningOn")),
        is_active=bool(pick(item, "isActive", "is_active") if pick(item, "isActive", "is_active") is not None else True),
        raw=item,
    )


def collect() -> int:
    total = 0
    for country in settings.meta_countries:
        records = [
            map_item(item, country)
            for item in run_actor(settings.meta_actor_id, build_input(country),
                                  max_items=settings.meta_results_limit * len(settings.meta_keywords))
        ]
        with session_scope() as session:
            total += upsert_ads(session, records)
    return total
