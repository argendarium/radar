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
