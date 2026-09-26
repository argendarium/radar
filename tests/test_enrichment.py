import pytest
from sqlalchemy import delete, select

from app.db import Product, ProductEnrichment, init_db, session_scope
from app.mapping import slugify
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
