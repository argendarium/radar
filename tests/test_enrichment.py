from sqlalchemy import select

from app.db import Product, ProductEnrichment, init_db, session_scope
from app.mapping import slugify


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
