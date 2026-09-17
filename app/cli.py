"""CLI del radar.

  python -m app.cli init-db
  python -m app.cli demo
  python -m app.cli run collect-meta | collect-tiktok | normalize | score | notify | pipeline
  python -m app.cli schema apify/facebook-ads-scraper
  python -m app.cli top
  python -m app.cli serve
"""
from __future__ import annotations

import argparse
import json

import httpx

from app.config import settings
from app.db import init_db


def cmd_schema(actor_id: str) -> None:
    """Imprime el input schema de un actor para ajustar build_input() y el JSON de TikTok."""
    if not settings.apify_token:
        raise SystemExit("Falta APIFY_TOKEN en .env")
    actor = actor_id.replace("/", "~")
    base = "https://api.apify.com/v2/acts"
    params = {"token": settings.apify_token}
    build = httpx.get(f"{base}/{actor}/builds/default", params=params, timeout=30)
    build.raise_for_status()
    data = build.json().get("data", {})
    schema = (data.get("actorDefinition") or {}).get("input") or data.get("inputSchema")
    if isinstance(schema, str):
        schema = json.loads(schema)
    if not schema:
        raise SystemExit("No se encontró input schema. Revisa la pestaña Input del actor en Apify Console.")
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    print(f"Actor: {actor_id}\n")
    for name, spec in props.items():
        flag = "requerido" if name in required else "opcional"
        default = spec.get("default", spec.get("prefill"))
        print(f"- {name} ({spec.get('type')}, {flag}) default={json.dumps(default, ensure_ascii=False)}")
        if spec.get("description"):
            print(f"    {spec['description'][:160]}")


def cmd_top(limit: int) -> None:
    from sqlalchemy import select

    from app.db import Product, session_scope
    with session_scope() as s:
        for p in s.scalars(select(Product).order_by(Product.score.desc()).limit(limit)):
            print(f"{p.score:5.1f}  {p.name:<40} L{p.s_longevity:>4.1f} C{p.s_copies:>4.1f} "
                  f"I{p.s_intensity:>4.1f} V{p.s_viability:>4.1f}  [{p.status}]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("demo")
    run = sub.add_parser("run")
    run.add_argument("job", choices=["collect-meta", "collect-tiktok", "normalize", "score", "notify", "pipeline"])
    schema = sub.add_parser("schema")
    schema.add_argument("actor_id")
    top = sub.add_parser("top")
    top.add_argument("--limit", type=int, default=10)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    init_db()
    if args.command == "init-db":
        print("Base de datos lista")
    elif args.command == "demo":
        from app.demo import seed
        print(f"{seed()} productos demo cargados")
    elif args.command == "run":
        from app.jobs import execute
        result = execute(args.job)
        print(f"[{result['status']}] {result['message']}")
    elif args.command == "schema":
        cmd_schema(args.actor_id)
    elif args.command == "top":
        cmd_top(args.limit)
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("app.api.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
