"""Extracción tolerante de campos: cada actor de Apify nombra distinto sus campos."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def get_path(data: Any, path: str) -> Any:
    """get_path(d, 'snapshot.images.0.originalImageUrl')"""
    cur = data
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            if not part.isdigit() or int(part) >= len(cur):
                return None
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def pick(data: Any, *paths: str) -> Any:
    """Devuelve el primer valor no vacío entre varias rutas candidatas."""
    for path in paths:
        value = get_path(data, path)
        if value not in (None, "", [], {}):
            return value
    return None


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    try:
        number = float(digits) if digits else None
    except ValueError:
        return None
    if number is None:
        return None
    text = str(value).lower()
    if text.endswith("k"):
        number *= 1_000
    elif text.endswith("m"):
        number *= 1_000_000
    return int(number)


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            ts = float(value)
            if ts > 1e12:  # milisegundos
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (ValueError, OSError, OverflowError):
        return None


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:150] or "sin-nombre"
