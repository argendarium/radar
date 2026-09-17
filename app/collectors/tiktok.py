"""Colector de TikTok Creative Center (Top Ads) vía Apify.

Hay varios actores comunitarios con inputs distintos. Configura:
  TIKTOK_ACTOR_ID en .env
  config/tiktok_input.json con el input exacto (ver `python -m app.cli schema <actor_id>`)
RD no suele estar entre los mercados de Creative Center: usa MX y CO como señal adelantada.
"""
from __future__ import annotations

import json

from app.collectors.base import AdRecord, CollectorError, run_actor, upsert_ads
from app.config import settings
from app.db import session_scope
from app.mapping import pick, to_datetime, to_int


def map_item(item: dict) -> AdRecord:
    external_id = pick(item, "adId", "ad_id", "id", "material_id", "materialId")
    return AdRecord(
        source="tiktok",
        external_id=str(external_id) if external_id else "",
        country=pick(item, "targetCountry", "country", "country_code", "region", "countries.0"),
        advertiser=pick(item, "brand", "brandName", "brand_name", "advertiser", "advertiserName"),
        text=pick(item, "adTitle", "ad_title", "adCopy", "title", "hookText"),
        image_url=pick(item, "thumbnailUrl", "thumbnail", "cover", "video_info.cover", "videoCover"),
        video_url=pick(item, "videoUrl", "video_url", "video_info.video_url.720p", "videoUrls.0"),
        landing_url=pick(item, "landingPage", "landing_page", "landingPageUrl"),
        likes=to_int(pick(item, "likeCount", "likes", "like")),
        comments=to_int(pick(item, "commentCount", "comments", "comment")),
        started_at=to_datetime(pick(item, "firstSeen", "first_seen", "createTime")),
        raw=item,
    )


def collect() -> int:
    if not settings.tiktok_actor_id:
        raise CollectorError("Falta TIKTOK_ACTOR_ID en .env")
    if not settings.tiktok_input_file.exists():
        raise CollectorError("Falta config/tiktok_input.json con el input del actor")
    run_input = json.loads(settings.tiktok_input_file.read_text(encoding="utf-8"))
    records = [map_item(item) for item in run_actor(settings.tiktok_actor_id, run_input)]
    with session_scope() as session:
        return upsert_ads(session, records)
