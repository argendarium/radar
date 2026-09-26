import pytest
from sqlalchemy import delete, select

from app.db import Product, ProductEnrichment, init_db, session_scope
from app.mapping import slugify, to_float
from app.services.providers.urls import UrlError, detect_source, extract_aliexpress_product_id, extract_amazon_asin


def test_product_enrichment_relationship():
    init_db()
    with session_scope() as s:
        product = Product(slug=slugify("producto test enrichment"), name="producto test enrichment")
        s.add(product)
        s.flush()
        s.add(ProductEnrichment(product_id=product.id, amazon_price=31.99))
        s.flush()
        product_id = product.id

    with session_scope() as s:
        product = s.scalar(select(Product).where(Product.id == product_id))
        assert product.enrichment is not None
        assert product.enrichment.amazon_price == 31.99

    # Cleanup: delete ProductEnrichment and Product to avoid polluting shared test DB
    with session_scope() as s:
        s.execute(delete(ProductEnrichment).where(ProductEnrichment.product_id == product_id))
        s.execute(delete(Product).where(Product.id == product_id))
        s.flush()


def test_detect_source():
    assert detect_source("https://www.amazon.com/dp/B0D1XCVTPB") == "amazon"
    assert detect_source("https://es.aliexpress.com/item/1005006123456789.html") == "aliexpress"
    assert detect_source("https://www.alibaba.com/product-detail/thing_123.html") == "alibaba"


def test_detect_source_unknown_raises():
    with pytest.raises(UrlError):
        detect_source("https://example.com/producto")


def test_detect_source_rejects_lookalike_domain():
    with pytest.raises(UrlError):
        detect_source("https://www.not-amazon.com/dp/B0D1XCVTPB")


def test_extract_amazon_asin():
    assert extract_amazon_asin("https://www.amazon.com/PHOFAY-Spray/dp/B0D1XCVTPB/ref=sr_1_1") == "B0D1XCVTPB"
    assert extract_amazon_asin("https://www.amazon.com/gp/product/B0D1XCVTPB") == "B0D1XCVTPB"


def test_extract_amazon_asin_invalid():
    with pytest.raises(UrlError):
        extract_amazon_asin("https://www.amazon.com/s?k=algo")


def test_extract_aliexpress_product_id():
    assert extract_aliexpress_product_id("https://es.aliexpress.com/item/1005006123456789.html") == "1005006123456789"


def test_extract_aliexpress_product_id_invalid():
    with pytest.raises(UrlError):
        extract_aliexpress_product_id("https://es.aliexpress.com/store/123456")


def test_to_float():
    assert to_float("$31.99") == 31.99
    assert to_float("4.0") == 4.0
    assert to_float(None) is None
    assert to_float("") is None


def test_fetch_amazon_signal(monkeypatch):
    from app.services.providers import amazon

    monkeypatch.setattr(amazon, "settings", type("S", (), {"rapidapi_key": "test-key"})())

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": {"asin": "B0D1XCVTPB", "product_price": "$31.99", "product_star_rating": "4.0",
                             "product_num_ratings": 89, "sales_volume": "5K+ bought in past month"}}

    def fake_get(url, params=None, headers=None, timeout=None):
        assert params["asin"] == "B0D1XCVTPB"
        assert headers["x-rapidapi-key"] == "test-key"
        return FakeResponse()

    monkeypatch.setattr(amazon.httpx, "get", fake_get)
    result = amazon.fetch_amazon_signal("https://www.amazon.com/dp/B0D1XCVTPB")
    assert result["price"] == 31.99
    assert result["rating"] == 4.0
    assert result["reviews_count"] == 89
    assert result["bought_last_month"] == "5K+ bought in past month"


def test_fetch_amazon_signal_missing_key(monkeypatch):
    from app.services.providers import amazon

    monkeypatch.setattr(amazon, "settings", type("S", (), {"rapidapi_key": ""})())
    with pytest.raises(amazon.AmazonProviderError):
        amazon.fetch_amazon_signal("https://www.amazon.com/dp/B0D1XCVTPB")


def test_fetch_amazon_signal_rate_limited(monkeypatch):
    from app.services.providers import amazon

    monkeypatch.setattr(amazon, "settings", type("S", (), {"rapidapi_key": "test-key"})())

    class RateLimited:
        status_code = 429

        def json(self):
            return {}

    monkeypatch.setattr(amazon.httpx, "get", lambda *a, **k: RateLimited())
    with pytest.raises(amazon.AmazonProviderError):
        amazon.fetch_amazon_signal("https://www.amazon.com/dp/B0D1XCVTPB")


def test_fetch_amazon_signal_malformed_response(monkeypatch):
    from app.services.providers import amazon

    monkeypatch.setattr(amazon, "settings", type("S", (), {"rapidapi_key": "test-key"})())

    class BadResponse:
        status_code = 200
        def json(self):
            return {"data": "not-a-dict"}

    monkeypatch.setattr(amazon.httpx, "get", lambda *a, **k: BadResponse())
    with pytest.raises(amazon.AmazonProviderError):
        amazon.fetch_amazon_signal("https://www.amazon.com/dp/B0D1XCVTPB")


def test_fetch_amazon_signal_invalid_url():
    from app.services.providers import amazon

    with pytest.raises(amazon.AmazonProviderError):
        amazon.fetch_amazon_signal("https://www.amazon.com/s?k=algo")


def test_sign_is_deterministic():
    from app.services.providers.aliexpress import _sign

    params_a = {"b": "2", "a": "1"}
    params_b = {"a": "1", "b": "2"}
    assert _sign(params_a, "secret") == _sign(params_b, "secret")
    assert _sign(params_a, "secret") == _sign(params_a, "secret").upper()


def test_fetch_sourcing_signal_aliexpress(monkeypatch):
    from app.services.providers import aliexpress

    monkeypatch.setattr(aliexpress, "settings", type("S", (), {
        "aliexpress_app_key": "key", "aliexpress_app_secret": "secret", "aliexpress_tracking_id": "track"})())

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"aliexpress_affiliate_productdetail_get_response": {"resp_result": {"result": {
                "products": {"product": [{"target_sale_price": "1.78", "shop_url": "https://aliexpress.com/store/123"}]}
            }}}}

    def fake_post(url, data=None, timeout=None):
        assert data["method"] == "aliexpress.affiliate.productdetail.get"
        assert data["product_ids"] == "1005006123456789"
        assert "sign" in data
        return FakeResponse()

    monkeypatch.setattr(aliexpress.httpx, "post", fake_post)
    result = aliexpress.fetch_sourcing_signal("https://es.aliexpress.com/item/1005006123456789.html")
    assert result["price_unit"] == 1.78
    assert result["supplier_name"] == "https://aliexpress.com/store/123"
    assert result["moq"] is None


def test_fetch_sourcing_signal_aliexpress_not_found(monkeypatch):
    from app.services.providers import aliexpress

    monkeypatch.setattr(aliexpress, "settings", type("S", (), {
        "aliexpress_app_key": "key", "aliexpress_app_secret": "secret", "aliexpress_tracking_id": "track"})())

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"aliexpress_affiliate_productdetail_get_response": {"resp_result": {"result": {"products": {}}}}}

    monkeypatch.setattr(aliexpress.httpx, "post", lambda *a, **k: FakeResponse())
    with pytest.raises(aliexpress.AliexpressProviderError):
        aliexpress.fetch_sourcing_signal("https://es.aliexpress.com/item/1005006123456789.html")


def test_fetch_sourcing_signal_aliexpress_missing_keys(monkeypatch):
    from app.services.providers import aliexpress

    monkeypatch.setattr(aliexpress, "settings", type("S", (), {
        "aliexpress_app_key": "", "aliexpress_app_secret": "", "aliexpress_tracking_id": ""})())
    with pytest.raises(aliexpress.AliexpressProviderError):
        aliexpress.fetch_sourcing_signal("https://es.aliexpress.com/item/1005006123456789.html")


def test_fetch_sourcing_signal_alibaba(monkeypatch):
    from app.services.providers import alibaba

    monkeypatch.setattr(alibaba, "settings", type("S", (), {
        "alibaba_apify_actor_id": "some/actor", "alibaba_max_charge_usd": 0.05})())
    fake_item = {"title": "Producto de prueba", "price": "$1.99", "minOrder": 10, "supplierName": "Proveedor X"}
    monkeypatch.setattr(
        alibaba, "run_actor",
        lambda actor_id, run_input, max_items=None, max_charge_usd=None: iter([fake_item]),
    )
    result = alibaba.fetch_sourcing_signal("https://www.alibaba.com/product-detail/thing_123.html")
    assert result["price_unit"] == 1.99
    assert result["moq"] == 10
    assert result["supplier_name"] == "Proveedor X"


def test_fetch_sourcing_signal_alibaba_no_results(monkeypatch):
    from app.services.providers import alibaba

    monkeypatch.setattr(alibaba, "settings", type("S", (), {
        "alibaba_apify_actor_id": "some/actor", "alibaba_max_charge_usd": 0.05})())
    monkeypatch.setattr(
        alibaba, "run_actor",
        lambda actor_id, run_input, max_items=None, max_charge_usd=None: iter([]),
    )
    with pytest.raises(alibaba.AlibabaProviderError):
        alibaba.fetch_sourcing_signal("https://www.alibaba.com/product-detail/thing_123.html")


def test_fetch_sourcing_signal_alibaba_missing_actor(monkeypatch):
    from app.services.providers import alibaba

    monkeypatch.setattr(alibaba, "settings", type("S", (), {
        "alibaba_apify_actor_id": "", "alibaba_max_charge_usd": 0.05})())
    with pytest.raises(alibaba.AlibabaProviderError):
        alibaba.fetch_sourcing_signal("https://www.alibaba.com/product-detail/thing_123.html")


def test_analyze_requires_at_least_one_url():
    from app.db import Product, init_db, session_scope
    from app.services import enrichment

    init_db()
    with session_scope() as s:
        product = Product(slug=slugify("producto sin links"), name="producto sin links")
        s.add(product)
        s.flush()
        with pytest.raises(ValueError):
            enrichment.analyze(product, None, None)
        product_id = product.id

    # Cleanup: evitar contaminar la base compartida de tests
    with session_scope() as s:
        s.execute(delete(Product).where(Product.id == product_id))
        s.flush()


def test_analyze_partial_failure(monkeypatch):
    from sqlalchemy import select

    from app.db import Product, init_db, session_scope
    from app.services import enrichment
    from app.services.providers import aliexpress, amazon

    init_db()
    monkeypatch.setattr(amazon, "fetch_amazon_signal",
                        lambda url: (_ for _ in ()).throw(amazon.AmazonProviderError("sin llave")))
    monkeypatch.setattr(aliexpress, "fetch_sourcing_signal",
                        lambda url: {"price_unit": 1.5, "supplier_name": "X", "moq": None, "raw": {}})

    with session_scope() as s:
        product = Product(slug=slugify("producto analyze parcial"), name="producto analyze parcial")
        s.add(product)
        s.flush()
        result = enrichment.analyze(product, "https://amazon.com/dp/B0D1XCVTPB",
                                    "https://aliexpress.com/item/123.html")
        product_id = product.id

    assert result["amazon"]["status"] == "error"
    assert result["sourcing"]["status"] == "ok"
    assert result["sourcing"]["price_unit"] == 1.5
    assert "raw" not in result["amazon"] and "raw" not in result["sourcing"]

    with session_scope() as s:
        product = s.scalar(select(Product).where(Product.id == product_id))
        assert product.enrichment.sourcing_price_unit == 1.5
        assert product.enrichment.amazon_price is None

    # Cleanup: evitar contaminar la base compartida de tests
    with session_scope() as s:
        s.execute(delete(ProductEnrichment).where(ProductEnrichment.product_id == product_id))
        s.execute(delete(Product).where(Product.id == product_id))
        s.flush()


def test_analyze_no_row_when_both_fail(monkeypatch):
    from sqlalchemy import select

    from app.db import Product, init_db, session_scope
    from app.services import enrichment
    from app.services.providers import aliexpress, amazon

    init_db()
    monkeypatch.setattr(amazon, "fetch_amazon_signal",
                        lambda url: (_ for _ in ()).throw(amazon.AmazonProviderError("sin llave")))
    monkeypatch.setattr(aliexpress, "fetch_sourcing_signal",
                        lambda url: (_ for _ in ()).throw(aliexpress.AliexpressProviderError("sin llave")))

    with session_scope() as s:
        product = Product(slug=slugify("producto ambos fallan"), name="producto ambos fallan")
        s.add(product)
        s.flush()
        result = enrichment.analyze(product, "https://amazon.com/dp/B0D1XCVTPB",
                                    "https://aliexpress.com/item/123.html")
        product_id = product.id

    assert result["amazon"]["status"] == "error"
    assert result["sourcing"]["status"] == "error"

    with session_scope() as s:
        product = s.scalar(select(Product).where(Product.id == product_id))
        assert product.enrichment is None

    # Cleanup: evitar contaminar la base compartida de tests
    with session_scope() as s:
        s.execute(delete(Product).where(Product.id == product_id))
        s.flush()


def test_analyze_endpoint_validation():
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.demo import seed

    with TestClient(app) as client:
        seed()
        pid = client.get("/api/products").json()[0]["id"]
        assert client.post(f"/api/products/{pid}/analyze", json={}).status_code == 400
        assert client.post("/api/products/999999/analyze", json={"amazon_url": "x"}).status_code == 404


def test_analyze_endpoint_happy_path(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.demo import seed
    from app.services import enrichment

    monkeypatch.setattr(enrichment, "analyze", lambda product, amazon_url, sourcing_url: {
        "amazon": {"status": "ok", "price": 31.99, "rating": 4.0, "reviews_count": 89, "bought_last_month": "5K+"},
        "sourcing": {"status": "skipped"},
    })

    with TestClient(app) as client:
        seed()
        pid = client.get("/api/products").json()[0]["id"]
        resp = client.post(f"/api/products/{pid}/analyze", json={"amazon_url": "https://amazon.com/dp/B0D1XCVTPB"})
        assert resp.status_code == 200
        assert resp.json()["amazon"]["price"] == 31.99
        detail = client.get(f"/api/products/{pid}").json()
        assert "enrichment" in detail  # el mock no persiste nada: sigue None, pero la llave debe existir
        assert detail["enrichment"] is None


def test_get_product_includes_saved_enrichment():
    from sqlalchemy import select

    from app.api.main import app
    from app.db import Product, ProductEnrichment, session_scope
    from app.demo import seed
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        seed()
        pid = client.get("/api/products").json()[0]["id"]
        with session_scope() as s:
            product = s.scalar(select(Product).where(Product.id == pid))
            product.enrichment = ProductEnrichment(product_id=pid, amazon_price=31.99, amazon_rating=4.0,
                                                    sourcing_source="aliexpress", sourcing_price_unit=1.78)
        detail = client.get(f"/api/products/{pid}").json()
        assert detail["enrichment"]["amazon_price"] == 31.99
        assert detail["enrichment"]["sourcing_source"] == "aliexpress"

    # Cleanup: evitar contaminar la base compartida de tests
    with session_scope() as s:
        s.execute(delete(ProductEnrichment).where(ProductEnrichment.product_id == pid))
        s.flush()
