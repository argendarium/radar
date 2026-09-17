from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.collectors.meta import map_item
from app.mapping import pick, slugify, to_datetime, to_int
from app.services.normalizer import _parse_json
from app.services.scorer import AdSignal, compute

NOW = datetime(2026, 9, 17)


def _ad(advertiser, days, likes=None):
    return AdSignal(advertiser, NOW - timedelta(days=days), NOW - timedelta(days=1), NOW, True, likes, None)


def test_winner_beats_new_product():
    winner = compute([_ad(f"tienda{i}", 40) for i in range(6)], 8, None, None)
    new = compute([_ad("tienda1", 3)], 8, None, None)
    assert winner["score"] > new["score"]
    assert winner["s_longevity"] == 10 and winner["s_copies"] == 10


def test_sizes_penalty():
    ads = [_ad(f"t{i}", 40) for i in range(6)]
    assert compute(ads, 8, None, None, has_sizes=True)["score"] < compute(ads, 8, None, None)["score"]


def test_margin_adjusts_viability():
    ads = [_ad("t1", 10)]
    good = compute(ads, 6, cost_usd=5, sale_price_dop=1500)   # 5x
    bad = compute(ads, 6, cost_usd=20, sale_price_dop=1500)   # 1.25x
    assert good["s_viability"] > bad["s_viability"]
    assert good["margin_ratio"] == 5.0


def test_mapping_helpers():
    data = {"snapshot": {"images": [{"originalImageUrl": "http://img"}]}}
    assert pick(data, "missing", "snapshot.images.0.originalImageUrl") == "http://img"
    assert to_int("1.2k") == 1200
    assert to_datetime(1735689600).year == 2025
    assert slugify("Selladora de Bolsas Portátil") == "selladora-de-bolsas-portatil"


def test_meta_item_mapping():
    item = {"adArchiveID": "123", "pageName": "Tienda RD", "startDate": 1754006400, "isActive": True,
            "snapshot": {"body": {"text": "Paga al recibir"}, "linkUrl": "https://x.do",
                         "videos": [{"videoPreviewImageUrl": "https://thumb", "videoHdUrl": "https://v"}]}}
    rec = map_item(item, "DO")
    assert rec.external_id == "123" and rec.advertiser == "Tienda RD"
    assert rec.image_url == "https://thumb" and rec.video_url == "https://v"
    assert rec.text == "Paga al recibir" and rec.started_at is not None


def test_parse_claude_json():
    assert _parse_json('```json\n{"nombre": "x", "wow": 7}\n```')["wow"] == 7


def test_api_flow():
    from app.api.main import app
    from app.demo import seed

    with TestClient(app) as client:
        seed()
        products = client.get("/api/products").json()
        assert len(products) == 10
        top = products[0]
        assert top["score"] >= products[-1]["score"]
        updated = client.patch(f"/api/products/{top['id']}",
                               json={"status": "en_prueba", "supplier_cost_usd": 4, "sale_price_dop": 1800}).json()
        assert updated["status"] == "en_prueba" and updated["margin_ratio"] == 7.5
        assert client.patch(f"/api/products/{top['id']}", json={"status": "otro"}).status_code == 422
        assert client.get("/api/products", params={"status": "en_prueba"}).json()[0]["id"] == top["id"]
        mx = client.get("/api/products", params={"country": "MX"}).json()
        assert mx and all("MX" in p["countries"] for p in mx)
        job = client.post("/api/jobs/score").json()
        assert job["status"] == "running"
        runs = client.get("/api/runs").json()
        assert runs[0]["kind"] == "score"
        assert client.get("/api/stats").json()["products"] == 10


def test_collect_and_normalize_pipeline(monkeypatch):
    """Colector Meta + normalización con Claude simulados: agrupa copias en un solo producto."""
    from sqlalchemy import select

    from app.collectors import meta
    from app.db import Ad, Product, init_db, session_scope
    from app.services import normalizer, scorer

    init_db()
    fake_items = [
        {"adArchiveID": f"x{i}", "pageName": f"Tienda {i}", "startDate": 1754006400,
         "snapshot": {"body": {"text": "Selladora portátil, paga al recibir"},
                      "images": [{"originalImageUrl": f"https://img/{i}.jpg"}]}}
        for i in range(3)
    ] + [{"adArchiveID": "curso1", "pageName": "Academia", "snapshot": {"body": {"text": "Curso online"}}}]

    monkeypatch.setattr(meta, "run_actor", lambda actor, run_input, max_items=None: iter(fake_items))
    n_countries = len(meta.settings.meta_countries)
    assert meta.collect() == len(fake_items) * n_countries

    def fake_claude(client, ad, names, with_image):
        if "Curso" in (ad.text or ""):
            return {"es_producto_fisico": False}
        return {"es_producto_fisico": True, "nombre": "Selladora de bolsas", "categoria": "cocina",
                "viabilidad": 8, "wow": 7, "tiene_tallas": False, "fragil": False, "peso": "ligero",
                "angulo": "Comida fresca", "hooks": ["a", "b", "c"]}

    monkeypatch.setattr(normalizer, "_ask_claude", fake_claude)
    monkeypatch.setattr(normalizer, "settings", type("S", (), {
        "anthropic_api_key": "test", "max_normalize_per_run": 50, "claude_model": "x"})())
    import sys, types
    fake_anthropic = types.SimpleNamespace(Anthropic=lambda api_key: object(),
                                           BadRequestError=type("B", (Exception,), {}),
                                           APIError=type("A", (Exception,), {}))
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    assert normalizer.normalize() >= 4
    scorer.score_all()
    with session_scope() as s:
        product = s.scalar(select(Product).where(Product.slug == "selladora-de-bolsas"))
        assert product is not None and len(product.ads) == 3  # mismo anuncio en varios países = un registro
        assert set(product.ads[0].country.split(",")) == set(meta.settings.meta_countries)
        assert product.score > 0
        curso = s.scalar(select(Ad).where(Ad.external_id == "curso1"))
        assert curso.is_product is False and curso.product_id is None
