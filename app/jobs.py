"""Orquestación de trabajos. Cada trabajo queda registrado en la tabla runs."""
from __future__ import annotations

import traceback
from typing import Callable

from app.db import Run, session_scope, utcnow


def _collect_meta() -> tuple[int, str]:
    from app.collectors import meta
    n = meta.collect()
    return n, f"{n} anuncios de Meta"


def _collect_tiktok() -> tuple[int, str]:
    from app.collectors import tiktok
    n = tiktok.collect()
    return n, f"{n} anuncios de TikTok"


def _normalize() -> tuple[int, str]:
    from app.services.normalizer import normalize
    n = normalize()
    return n, f"{n} anuncios normalizados con Claude"


def _score() -> tuple[int, str]:
    from app.services.scorer import score_all
    n = score_all()
    return n, f"{n} productos puntuados"


def _notify() -> tuple[int, str]:
    from app.services.notify import send_top
    return 1, send_top()


def _pipeline() -> tuple[int, str]:
    """Corre todo en orden. Un colector que falla no detiene el resto."""
    notes, total = [], 0
    for name, step in (("meta", _collect_meta), ("tiktok", _collect_tiktok), ("normalizar", _normalize),
                       ("score", _score), ("alerta", _notify)):
        try:
            n, msg = step()
            total += n
            notes.append(msg)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{name}: {exc}")
    return total, " | ".join(notes)


JOBS: dict[str, Callable[[], tuple[int, str]]] = {
    "collect-meta": _collect_meta,
    "collect-tiktok": _collect_tiktok,
    "normalize": _normalize,
    "score": _score,
    "notify": _notify,
    "pipeline": _pipeline,
}


EXPECTED_ERRORS = {"CollectorError", "NormalizerError"}  # errores de configuración: sin traceback


def start_run(kind: str) -> int:
    with session_scope() as session:
        run = Run(kind=kind)
        session.add(run)
        session.flush()
        return run.id


def execute(kind: str, run_id: int | None = None) -> dict:
    if kind not in JOBS:
        raise KeyError(kind)
    run_id = run_id or start_run(kind)
    try:
        items, message = JOBS[kind]()
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        items, message, status = 0, str(exc), "error"
        if type(exc).__name__ not in EXPECTED_ERRORS:
            traceback.print_exc()
    with session_scope() as session:
        run = session.get(Run, run_id)
        run.status, run.message, run.items, run.finished_at = status, message, items, utcnow()
    return {"id": run_id, "kind": kind, "status": status, "items": items, "message": message}
