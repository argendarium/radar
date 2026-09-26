# Analizador de producto candidato — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar pegar el link exacto de Amazon y de AliExpress/Alibaba de un producto candidato y traer automáticamente demanda (rating, reseñas, comprado el mes pasado) y costo de sourcing (precio, MOQ, proveedor) al panel de detalle del radar.

**Architecture:** Tres módulos de proveedor independientes (`app/services/providers/{amazon,aliexpress,alibaba}.py`) que reciben una URL y devuelven un dict con la señal o lanzan su propio error tipado. Un orquestador (`app/services/enrichment.py`) los llama, nunca falla todo por uno, y persiste el resultado en una tabla nueva `product_enrichment` (uno a uno con `Product`, se sobrescribe en cada re-análisis). Un endpoint (`POST /api/products/{id}/analyze`) y un comando CLI exponen el mismo orquestador. El dashboard agrega una tarjeta "Datos externos" con el formulario de links y un botón para copiar el costo de sourcing al campo de margen que ya existe.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2, httpx (ya en requirements.txt), apify-client (ya en requirements.txt), vanilla JS en `dashboard/index.html`.

## Global Constraints

- Español, sentence case, sin emojis en ningún lugar (UI, código, commits, logs).
- Diagnosticar primero, cambios puntuales; no reescrituras completas de archivos existentes.
- Mantener los tokens de color/tipografía de `dashboard/index.html`; probar escritorio, móvil y modo oscuro.
- Backend orientado a APIs: el análisis debe poder correr por CLI y por API, igual que los demás servicios.
- Escapar siempre texto externo antes de insertarlo en el HTML del dashboard (usar la función `esc()` ya existente).
- `make test` debe pasar antes de dar cualquier tarea por terminada.
- On-demand únicamente: nunca se analiza automáticamente a todos los productos.
- Cada fuente (Amazon / AliExpress / Alibaba) falla de forma independiente — un error en una nunca bloquea el resultado de la otra.
- Reutilizar patrones existentes del proyecto: `app/mapping.py` para extracción tolerante de campos, `app/collectors/base.py::run_actor()` para Apify, monkeypatch de objetos de módulo completo (no atributos sueltos de `settings`, que es un dataclass frozen) en los tests.

---

### Task 1: Modelo `ProductEnrichment`

**Files:**
- Modify: `app/db.py:69` (agregar relación en `Product`) y después de la clase `Ad` (línea 97) (agregar clase nueva)
- Test: `tests/test_enrichment.py` (crear)

**Interfaces:**
- Produces: `ProductEnrichment` (modelo SQLAlchemy) con columnas `product_id, amazon_url, amazon_price, amazon_rating, amazon_reviews_count, amazon_bought_last_month, amazon_fetched_at, sourcing_source, sourcing_url, sourcing_price_unit, sourcing_moq, sourcing_supplier_name, sourcing_fetched_at, raw_amazon, raw_sourcing`. `Product.enrichment` (relación uno a uno, `None` si no se ha analizado).

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_enrichment.py`:

```python
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: FAIL con `ImportError: cannot import name 'ProductEnrichment'`

- [ ] **Step 3: Agregar el modelo**

En `app/db.py`, dentro de la clase `Product` (después de la línea `ads: Mapped[list["Ad"]] = relationship(back_populates="product")`, línea 69), agregar:

```python
    enrichment: Mapped["ProductEnrichment | None"] = relationship(back_populates="product", uselist=False)
```

Después de la clase `Ad` completa (después de la línea 96, antes de `class Run(Base):`), agregar:

```python
class ProductEnrichment(Base):
    """Números externos de un producto candidato, traídos on-demand desde un link pegado por el operador."""
    __tablename__ = "product_enrichment"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True, index=True)

    amazon_url: Mapped[str | None] = mapped_column(Text)
    amazon_price: Mapped[float | None] = mapped_column(Float)
    amazon_rating: Mapped[float | None] = mapped_column(Float)
    amazon_reviews_count: Mapped[int | None] = mapped_column(Integer)
    amazon_bought_last_month: Mapped[str | None] = mapped_column(String(40))
    amazon_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)

    sourcing_source: Mapped[str | None] = mapped_column(String(20))  # aliexpress | alibaba
    sourcing_url: Mapped[str | None] = mapped_column(Text)
    sourcing_price_unit: Mapped[float | None] = mapped_column(Float)
    sourcing_moq: Mapped[int | None] = mapped_column(Integer)
    sourcing_supplier_name: Mapped[str | None] = mapped_column(String(200))
    sourcing_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)

    raw_amazon: Mapped[dict | None] = mapped_column(JSON)
    raw_sourcing: Mapped[dict | None] = mapped_column(JSON)

    product: Mapped[Product] = relationship(back_populates="enrichment")
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_enrichment.py
git commit -m "feat: agregar modelo ProductEnrichment"
```

---

### Task 2: Extracción de IDs desde URLs pegadas

**Files:**
- Create: `app/services/providers/__init__.py` (vacío)
- Create: `app/services/providers/urls.py`
- Test: `tests/test_enrichment.py` (agregar)

**Interfaces:**
- Produces: `UrlError(ValueError)`, `detect_source(url: str) -> str` (`"amazon" | "aliexpress" | "alibaba"`, o lanza `UrlError`), `extract_amazon_asin(url: str) -> str`, `extract_aliexpress_product_id(url: str) -> str`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_enrichment.py`:

```python
import pytest

from app.services.providers.urls import UrlError, detect_source, extract_aliexpress_product_id, extract_amazon_asin


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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v -k url_or_detect_or_extract`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.providers'`

- [ ] **Step 3: Crear el paquete y las funciones**

Crear `app/services/providers/__init__.py` vacío.

Crear `app/services/providers/urls.py`:

```python
"""Extrae identificadores de producto desde links que el operador pega a mano."""
from __future__ import annotations

import re
from urllib.parse import urlparse


class UrlError(ValueError):
    pass


def detect_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "amazon." in host:
        return "amazon"
    if "aliexpress." in host:
        return "aliexpress"
    if "alibaba." in host:
        return "alibaba"
    raise UrlError(f"No reconozco el sitio de este link: {url}")


def extract_amazon_asin(url: str) -> str:
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    if not match:
        raise UrlError("No encontré un ASIN válido en el link de Amazon (busco /dp/ASIN o /gp/product/ASIN)")
    return match.group(1)


def extract_aliexpress_product_id(url: str) -> str:
    match = re.search(r"/item/(?:[^/]*?)?(\d+)\.html", url) or re.search(r"[?&]productId=(\d+)", url)
    if not match:
        raise UrlError("No encontré un ID de producto válido en el link de AliExpress (busco /item/<id>.html)")
    return match.group(1)
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: PASS (todos los tests del archivo)

- [ ] **Step 5: Commit**

```bash
git add app/services/providers/__init__.py app/services/providers/urls.py tests/test_enrichment.py
git commit -m "feat: extraer ASIN de Amazon e ID de AliExpress desde URLs pegadas"
```

---

### Task 3: Config nueva + helper `to_float` + proveedor de Amazon

**Files:**
- Modify: `app/config.py` (después de la línea 69, `telegram_chat_id`)
- Modify: `.env.example` (al final del archivo)
- Modify: `app/mapping.py` (después de `to_int`, línea 53)
- Create: `app/services/providers/amazon.py`
- Test: `tests/test_enrichment.py` (agregar)

**Interfaces:**
- Consumes: `extract_amazon_asin` de Task 2.
- Produces: `settings.rapidapi_key`, `settings.aliexpress_app_key`, `settings.aliexpress_app_secret`, `settings.aliexpress_tracking_id`, `settings.alibaba_apify_actor_id`, `settings.alibaba_max_charge_usd` (todo el bloque de config del feature, para que las Tasks 4 y 5 no vuelvan a tocar `config.py`). `to_float(value) -> float | None` en `app/mapping.py`. `AmazonProviderError(RuntimeError)`, `fetch_amazon_signal(url: str) -> dict` con llaves `price, rating, reviews_count, bought_last_month, raw`.

- [ ] **Step 1: Agregar la config (sin test dedicado — son solo variables de entorno, igual que el resto de `config.py`)**

En `app/config.py`, después de la línea `telegram_chat_id: str = _env("TELEGRAM_CHAT_ID", "")` (línea 69), agregar:

```python

    # Analizador de producto: fuentes externas on-demand (opcional)
    rapidapi_key: str = _env("RAPIDAPI_KEY", "")
    aliexpress_app_key: str = _env("ALIEXPRESS_APP_KEY", "")
    aliexpress_app_secret: str = _env("ALIEXPRESS_APP_SECRET", "")
    aliexpress_tracking_id: str = _env("ALIEXPRESS_TRACKING_ID", "")
    alibaba_apify_actor_id: str = _env("ALIBABA_APIFY_ACTOR_ID", "")
    alibaba_max_charge_usd: float = _float("ALIBABA_MAX_CHARGE_USD", 0.05)
```

Al final de `.env.example`, agregar:

```

# Analizador de producto (opcional): números externos para un candidato, on-demand
# RapidAPI "Real-Time Amazon Data" (tier gratis: 100 requests/mes): https://rapidapi.com/letscrape-6bRBa3QguO5/api/real-time-amazon-data
RAPIDAPI_KEY=
# AliExpress Affiliate API (gratis, aprobación en portals.aliexpress.com)
ALIEXPRESS_APP_KEY=
ALIEXPRESS_APP_SECRET=
ALIEXPRESS_TRACKING_ID=
# Actor de Apify para Alibaba (elige uno en Apify Store, ej. dami_studio/alibaba-com-scraper)
ALIBABA_APIFY_ACTOR_ID=
ALIBABA_MAX_CHARGE_USD=0.05
```

- [ ] **Step 2: Escribir los tests que fallan (helper `to_float` + proveedor de Amazon)**

Agregar a `tests/test_enrichment.py`:

```python
from app.mapping import to_float


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
```

(`pytest` ya está importado por Task 2 en la parte de arriba del archivo; si se ejecuta esta task de forma aislada, agregar `import pytest` al inicio de `tests/test_enrichment.py`.)

- [ ] **Step 3: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v -k "to_float or fetch_amazon"`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.providers.amazon'`

- [ ] **Step 4: Implementar `to_float` y el proveedor de Amazon**

En `app/mapping.py`, después de la función `to_int` (línea 53), agregar:

```python
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
```

Crear `app/services/providers/amazon.py`:

```python
"""Señal de demanda en Amazon vía RapidAPI 'Real-Time Amazon Data' (tier gratis: 100 requests/mes)."""
from __future__ import annotations

import httpx

from app.config import settings
from app.mapping import to_float, to_int
from app.services.providers.urls import extract_amazon_asin

RAPIDAPI_HOST = "real-time-amazon-data.p.rapidapi.com"


class AmazonProviderError(RuntimeError):
    pass


def fetch_amazon_signal(url: str) -> dict:
    if not settings.rapidapi_key:
        raise AmazonProviderError("Falta RAPIDAPI_KEY en .env")
    asin = extract_amazon_asin(url)
    try:
        resp = httpx.get(
            f"https://{RAPIDAPI_HOST}/product-details",
            params={"asin": asin, "country": "US"},
            headers={"x-rapidapi-key": settings.rapidapi_key, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise AmazonProviderError(f"No se pudo conectar con Amazon: {exc}") from exc
    if resp.status_code == 429:
        raise AmazonProviderError("Límite mensual de Amazon alcanzado (tier gratis de RapidAPI)")
    if resp.status_code != 200:
        raise AmazonProviderError(f"Amazon respondió {resp.status_code}")
    data = (resp.json() or {}).get("data") or {}
    if not data:
        raise AmazonProviderError("Amazon no encontró ese producto")
    return {
        "price": to_float(data.get("product_price")),
        "rating": to_float(data.get("product_star_rating")),
        "reviews_count": to_int(data.get("product_num_ratings")),
        "bought_last_month": data.get("sales_volume"),
        "raw": data,
    }
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: PASS (todos)

- [ ] **Step 6: Commit**

```bash
git add app/config.py .env.example app/mapping.py app/services/providers/amazon.py tests/test_enrichment.py
git commit -m "feat: agregar proveedor de demanda en Amazon vía RapidAPI"
```

---

### Task 4: Proveedor de sourcing en AliExpress

**Files:**
- Create: `app/services/providers/aliexpress.py`
- Test: `tests/test_enrichment.py` (agregar)

**Interfaces:**
- Consumes: `extract_aliexpress_product_id` (Task 2), `settings.aliexpress_app_key/app_secret/tracking_id` (Task 3), `to_float` (Task 3).
- Produces: `AliexpressProviderError(RuntimeError)`, `fetch_sourcing_signal(url: str) -> dict` con llaves `price_unit, moq, supplier_name, raw`.

Nota sobre el endpoint: la API de afiliados de AliExpress usa la puerta de enlace `http://gw.api.taobao.com/router/rest` con firma MD5 (parámetros ordenados alfabéticamente, concatenados y envueltos con el app secret). Si al activar credenciales reales AliExpress ya migró a la puerta `https://api-sg.aliexpress.com/sync`, solo hay que cambiar `ALIEXPRESS_GATEWAY` — la firma y los parámetros no cambian. Verificar con una llamada real de prueba al tener `ALIEXPRESS_APP_KEY`/`ALIEXPRESS_APP_SECRET` reales, igual que ya haces con `python -m app.cli schema <actor_id>` para los actores de Apify.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_enrichment.py`:

```python
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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v -k aliexpress_or_sign`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.providers.aliexpress'`

- [ ] **Step 3: Implementar el proveedor**

Crear `app/services/providers/aliexpress.py`:

```python
"""Costo de sourcing en AliExpress vía la API oficial de afiliados (gratis).

Aprobación de la llave en portals.aliexpress.com > Tools > Dropshipping and Affiliates developer API.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.mapping import to_float
from app.services.providers.urls import extract_aliexpress_product_id

ALIEXPRESS_GATEWAY = "http://gw.api.taobao.com/router/rest"
_SHANGHAI = timezone(timedelta(hours=8))


class AliexpressProviderError(RuntimeError):
    pass


def _sign(params: dict, secret: str) -> str:
    ordered = sorted(params.items())
    base = "".join(f"{k}{v}" for k, v in ordered)
    wrapped = f"{secret}{base}{secret}"
    return hashlib.md5(wrapped.encode("utf-8")).hexdigest().upper()


def fetch_sourcing_signal(url: str) -> dict:
    if not (settings.aliexpress_app_key and settings.aliexpress_app_secret):
        raise AliexpressProviderError("Falta ALIEXPRESS_APP_KEY o ALIEXPRESS_APP_SECRET en .env")
    product_id = extract_aliexpress_product_id(url)
    params = {
        "app_key": settings.aliexpress_app_key,
        "method": "aliexpress.affiliate.productdetail.get",
        "sign_method": "md5",
        "timestamp": datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "product_ids": product_id,
        "target_currency": "USD",
        "target_language": "ES",
        "tracking_id": settings.aliexpress_tracking_id,
    }
    params["sign"] = _sign(params, settings.aliexpress_app_secret)
    try:
        resp = httpx.post(ALIEXPRESS_GATEWAY, data=params, timeout=20)
    except httpx.HTTPError as exc:
        raise AliexpressProviderError(f"No se pudo conectar con AliExpress: {exc}") from exc
    if resp.status_code != 200:
        raise AliexpressProviderError(f"AliExpress respondió {resp.status_code}")
    body = resp.json()
    if "error_response" in body:
        raise AliexpressProviderError(body["error_response"].get("msg", "Error de AliExpress"))
    products = (
        body.get("aliexpress_affiliate_productdetail_get_response", {})
        .get("resp_result", {}).get("result", {}).get("products", {}).get("product", [])
    )
    if not products:
        raise AliexpressProviderError("AliExpress no encontró ese producto")
    product = products[0]
    return {
        "price_unit": to_float(product.get("target_sale_price")),
        "moq": None,  # AliExpress es venta al detalle; el MOQ real vive en Alibaba
        "supplier_name": product.get("shop_url"),
        "raw": product,
    }
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add app/services/providers/aliexpress.py tests/test_enrichment.py
git commit -m "feat: agregar proveedor de sourcing en AliExpress"
```

---

### Task 5: `run_actor` con tope de gasto propio + proveedor de sourcing en Alibaba

**Files:**
- Modify: `app/collectors/base.py:46-64` (`run_actor`)
- Create: `app/services/providers/alibaba.py`
- Test: `tests/test_enrichment.py` (agregar)

**Interfaces:**
- Consumes: `run_actor` (modificado), `CollectorError` de `app/collectors/base.py`; `pick`, `to_int`, `to_float` de `app/mapping.py`; `settings.alibaba_apify_actor_id/alibaba_max_charge_usd` (Task 3).
- Produces: `run_actor(actor_id, run_input, max_items=None, max_charge_usd=None)` (nuevo parámetro opcional, no rompe a `collectors/meta.py` ni `collectors/tiktok.py` que no lo pasan). `AlibabaProviderError(RuntimeError)`, `fetch_sourcing_signal(url: str) -> dict` con llaves `price_unit, moq, supplier_name, raw`.

No se agrega un test nuevo para el cambio de `run_actor` en sí: el proyecto nunca prueba `run_actor` directamente (los colectores existentes mockean su propia referencia a `run_actor`, ver `test_collect_and_normalize_pipeline` en `tests/test_radar.py`). El cambio es un parámetro opcional con default `None` que cae al comportamiento actual (`settings.apify_max_charge_usd`), así que no cambia nada para los llamadores existentes. La cobertura real viene del test de `alibaba.fetch_sourcing_signal`, que mockea `alibaba.run_actor` igual que los colectores mockean el suyo.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_enrichment.py`:

```python
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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v -k alibaba`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.providers.alibaba'`

- [ ] **Step 3: Ajustar `run_actor` y crear el proveedor**

En `app/collectors/base.py`, reemplazar la firma y el cuerpo de `run_actor` (líneas 46-57):

```python
def run_actor(actor_id: str, run_input: dict, max_items: int | None = None,
              max_charge_usd: float | None = None) -> Iterator[dict]:
    """Ejecuta un actor de Apify, espera a que termine y devuelve sus items."""
    if not settings.apify_token:
        raise CollectorError("Falta APIFY_TOKEN en .env")
    from apify_client import ApifyClient

    client = ApifyClient(settings.apify_token)
    charge = max_charge_usd if max_charge_usd is not None else settings.apify_max_charge_usd
    run = client.actor(actor_id).call(
        run_input=run_input,
        max_items=max_items,
        max_total_charge_usd=Decimal(str(charge)),
    )
```

(el resto de la función, desde `if run is None:`, queda igual).

Crear `app/services/providers/alibaba.py`:

```python
"""Costo de sourcing en Alibaba vía un actor de Apify de una sola URL.

IMPORTANTE: el input y los nombres de campos dependen del actor elegido en Apify Store.
Antes de fijar ALIBABA_APIFY_ACTOR_ID, corre: python -m app.cli schema <actor_id>
y ajusta build_input() y map_item(), igual que con los colectores de Meta/TikTok.
"""
from __future__ import annotations

from app.collectors.base import CollectorError, run_actor
from app.config import settings
from app.mapping import pick, to_float, to_int


class AlibabaProviderError(RuntimeError):
    pass


def build_input(url: str) -> dict:
    return {"startUrls": [{"url": url}]}


def map_item(item: dict) -> dict:
    return {
        "price_unit": to_float(pick(item, "price", "minPrice", "price_min", "priceRange.0")),
        "moq": to_int(pick(item, "moq", "minOrder", "min_order_quantity")),
        "supplier_name": pick(item, "supplierName", "companyName", "seller", "storeName"),
        "raw": item,
    }


def fetch_sourcing_signal(url: str) -> dict:
    if not settings.alibaba_apify_actor_id:
        raise AlibabaProviderError("Falta ALIBABA_APIFY_ACTOR_ID en .env")
    try:
        items = list(run_actor(settings.alibaba_apify_actor_id, build_input(url), max_items=1,
                               max_charge_usd=settings.alibaba_max_charge_usd))
    except CollectorError as exc:
        raise AlibabaProviderError(str(exc)) from exc
    if not items:
        raise AlibabaProviderError("Alibaba no devolvió datos para ese link")
    return map_item(items[0])
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add app/collectors/base.py app/services/providers/alibaba.py tests/test_enrichment.py
git commit -m "feat: agregar proveedor de sourcing en Alibaba y tope de gasto propio en run_actor"
```

---

### Task 6: Orquestador `app/services/enrichment.py`

**Files:**
- Create: `app/services/enrichment.py`
- Test: `tests/test_enrichment.py` (agregar)

**Interfaces:**
- Consumes: `Product`, `ProductEnrichment`, `utcnow` de `app/db.py` (Task 1); módulos `app.services.providers.{amazon,aliexpress,alibaba}` y `UrlError` de `urls.py` (Tasks 2-5).
- Produces: `analyze(product: Product, amazon_url: str | None, sourcing_url: str | None) -> dict`. Devuelve `{"amazon": {...}, "sourcing": {...}}`, cada uno con `status` en `"ok" | "error" | "skipped"`. Lanza `ValueError` si ambos links vienen vacíos. Muta `product.enrichment` solo cuando al menos una fuente tuvo éxito (o ya existía una fila previa que actualizar).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_enrichment.py`:

```python
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
```

(`slugify` ya está importado arriba del archivo por Task 1; si esta task corre aislada, agregar `from app.mapping import slugify` al inicio de `tests/test_enrichment.py`.)

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v -k analyze`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.enrichment'`

- [ ] **Step 3: Implementar el orquestador**

Crear `app/services/enrichment.py`:

```python
"""Orquesta el análisis on-demand de un candidato con links pegados por el operador.

Cada fuente (Amazon / AliExpress / Alibaba) es independiente: si una falla, la otra
se guarda igual. Nunca se llama automáticamente para todos los productos.
"""
from __future__ import annotations

from app.db import Product, ProductEnrichment, utcnow
from app.services.providers import alibaba, aliexpress, amazon
from app.services.providers.urls import UrlError, detect_source


def _result(status: str, **extra) -> dict:
    return {"status": status, **extra}


def _fetch_amazon(url: str | None) -> dict:
    if not url:
        return _result("skipped")
    try:
        signal = amazon.fetch_amazon_signal(url)
    except (UrlError, amazon.AmazonProviderError) as exc:
        return _result("error", message=str(exc))
    return _result("ok", **signal)


def _fetch_sourcing(url: str | None) -> dict:
    if not url:
        return _result("skipped")
    try:
        source = detect_source(url)
    except UrlError as exc:
        return _result("error", message=str(exc))
    if source == "amazon":
        return _result("error", source=source,
                       message="Pega un link de AliExpress o Alibaba, no de Amazon, en el campo de sourcing")
    fetcher = aliexpress.fetch_sourcing_signal if source == "aliexpress" else alibaba.fetch_sourcing_signal
    try:
        signal = fetcher(url)
    except (UrlError, aliexpress.AliexpressProviderError, alibaba.AlibabaProviderError) as exc:
        return _result("error", source=source, message=str(exc))
    return _result("ok", source=source, **signal)


def analyze(product: Product, amazon_url: str | None, sourcing_url: str | None) -> dict:
    if not amazon_url and not sourcing_url:
        raise ValueError("Pega al menos un link para analizar")
    amazon_result = _fetch_amazon(amazon_url)
    sourcing_result = _fetch_sourcing(sourcing_url)

    if amazon_result["status"] == "ok" or sourcing_result["status"] == "ok" or product.enrichment is not None:
        enrichment = product.enrichment or ProductEnrichment(product_id=product.id)
        now = utcnow()
        if amazon_result["status"] == "ok":
            enrichment.amazon_url = amazon_url
            enrichment.amazon_price = amazon_result.get("price")
            enrichment.amazon_rating = amazon_result.get("rating")
            enrichment.amazon_reviews_count = amazon_result.get("reviews_count")
            enrichment.amazon_bought_last_month = amazon_result.get("bought_last_month")
            enrichment.raw_amazon = amazon_result.get("raw")
            enrichment.amazon_fetched_at = now
        if sourcing_result["status"] == "ok":
            enrichment.sourcing_source = sourcing_result.get("source")
            enrichment.sourcing_url = sourcing_url
            enrichment.sourcing_price_unit = sourcing_result.get("price_unit")
            enrichment.sourcing_moq = sourcing_result.get("moq")
            enrichment.sourcing_supplier_name = sourcing_result.get("supplier_name")
            enrichment.raw_sourcing = sourcing_result.get("raw")
            enrichment.sourcing_fetched_at = now
        product.enrichment = enrichment

    return {
        "amazon": {k: v for k, v in amazon_result.items() if k != "raw"},
        "sourcing": {k: v for k, v in sourcing_result.items() if k != "raw"},
    }
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add app/services/enrichment.py tests/test_enrichment.py
git commit -m "feat: agregar orquestador de analisis de producto (enrichment)"
```

---

### Task 7: Endpoint `POST /api/products/{id}/analyze` + exponer datos en el detalle

**Files:**
- Modify: `app/api/main.py`
- Test: `tests/test_enrichment.py` (agregar)

**Interfaces:**
- Consumes: `enrichment.analyze` (Task 6), `ProductEnrichment` (Task 1).
- Produces: `POST /api/products/{id}/analyze` → 200 con `{"amazon": {...}, "sourcing": {...}}`, 400 si ambos links vienen vacíos, 404 si el producto no existe. `GET /api/products/{id}` ahora incluye la llave `"enrichment"` (dict con los campos guardados, o `null` si nunca se analizó).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_enrichment.py`:

```python
def test_analyze_endpoint_validation():
    from app.api.main import app
    from app.demo import seed

    with TestClient(app) as client:
        seed()
        pid = client.get("/api/products").json()[0]["id"]
        assert client.post(f"/api/products/{pid}/analyze", json={}).status_code == 400
        assert client.post("/api/products/999999/analyze", json={"amazon_url": "x"}).status_code == 404


def test_analyze_endpoint_happy_path(monkeypatch):
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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v -k analyze_endpoint_or_includes_saved`
Expected: FAIL con 404 (ruta no existe) o `KeyError: 'enrichment'`

- [ ] **Step 3: Implementar el endpoint**

En `app/api/main.py`, agregar el import (junto a la línea 16, `from app.services import scorer`):

```python
from app.services import enrichment, scorer
```

Agregar una función después de `product_detail` (después de la línea 64) que arme el dict de enriquecimiento, y usarla dentro de `product_detail`:

```python
def enrichment_dict(p: Product) -> dict | None:
    e = p.enrichment
    if not e:
        return None
    return {
        "amazon_url": e.amazon_url, "amazon_price": e.amazon_price, "amazon_rating": e.amazon_rating,
        "amazon_reviews_count": e.amazon_reviews_count, "amazon_bought_last_month": e.amazon_bought_last_month,
        "amazon_fetched_at": _iso(e.amazon_fetched_at),
        "sourcing_source": e.sourcing_source, "sourcing_url": e.sourcing_url,
        "sourcing_price_unit": e.sourcing_price_unit, "sourcing_moq": e.sourcing_moq,
        "sourcing_supplier_name": e.sourcing_supplier_name, "sourcing_fetched_at": _iso(e.sourcing_fetched_at),
    }
```

En `product_detail` (línea 47-64), agregar `"enrichment": enrichment_dict(p),` dentro del `data.update({...})` (por ejemplo, justo después de `"usd_to_dop": settings.usd_to_dop,` en la línea 54).

Agregar el modelo de request y el endpoint después de `ProductUpdate` (después de la línea 71):

```python
class AnalyzeRequest(BaseModel):
    amazon_url: str | None = None
    sourcing_url: str | None = None
```

Agregar el endpoint después de `update_product` (después de la línea 139):

```python
@app.post("/api/products/{product_id}/analyze")
def analyze_product(product_id: int, payload: AnalyzeRequest) -> dict:
    with session_scope() as s:
        p = s.scalar(select(Product).options(selectinload(Product.ads)).where(Product.id == product_id))
        if not p:
            raise HTTPException(404, "Producto no encontrado")
        try:
            result = enrichment.analyze(p, payload.amazon_url, payload.sourcing_url)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        s.flush()
        return result
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Correr toda la suite para verificar que no se rompió nada**

Run: `.venv/bin/pytest -q`
Expected: PASS (todos los tests, incluyendo `tests/test_radar.py`)

- [ ] **Step 6: Commit**

```bash
git add app/api/main.py tests/test_enrichment.py
git commit -m "feat: exponer endpoint de analisis y datos externos en el detalle del producto"
```

---

### Task 8: Comando CLI `analyze`

**Files:**
- Modify: `app/cli.py`

**Interfaces:**
- Consumes: `enrichment.analyze` (Task 6).
- Produces: `python -m app.cli analyze <product_id> --amazon-url URL --sourcing-url URL`.

No lleva test automatizado: el CLI de este proyecto es una envoltura delgada sin tests dedicados (`cmd_schema`, `cmd_top` tampoco los tienen); la lógica real ya está cubierta por los tests de `enrichment.analyze` en la Task 6. La verificación es manual, en el Step 3.

- [ ] **Step 1: Actualizar el docstring del módulo**

En `app/cli.py`, en el docstring inicial (líneas 1-9), agregar una línea después de `python -m app.cli top`:

```
  python -m app.cli analyze <product_id> --amazon-url URL --sourcing-url URL
```

- [ ] **Step 2: Agregar el subcomando**

En `app/cli.py`, después del bloque `top = sub.add_parser("top"); top.add_argument(...)` (líneas 66-67), agregar:

```python
    analyze = sub.add_parser("analyze")
    analyze.add_argument("product_id", type=int)
    analyze.add_argument("--amazon-url", default=None)
    analyze.add_argument("--sourcing-url", default=None)
```

En el bloque de dispatch dentro de `main()`, después de `elif args.command == "top": cmd_top(args.limit)` (línea 86), agregar:

```python
    elif args.command == "analyze":
        from sqlalchemy import select

        from app.db import Product, session_scope
        from app.services import enrichment

        with session_scope() as s:
            product = s.scalar(select(Product).where(Product.id == args.product_id))
            if not product:
                raise SystemExit(f"Producto {args.product_id} no encontrado")
            result = enrichment.analyze(product, args.amazon_url, args.sourcing_url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
```

- [ ] **Step 3: Verificación manual**

Run: `.venv/bin/python -m app.cli demo && .venv/bin/python -m app.cli top --limit 1`

Tomar el `id` del primer producto impreso (o consultarlo con `.venv/bin/python -c "from app.db import Product, session_scope; from sqlalchemy import select;
with session_scope() as s: print(s.scalars(select(Product.id).order_by(Product.score.desc())).first())"`).

Run: `.venv/bin/python -m app.cli analyze <id>` (sin links)
Expected: `SystemExit` con el mensaje `Pega al menos un link para analizar` (viene de `enrichment.analyze`, propagado como excepción no capturada — aceptable para un comando manual de diagnóstico).

Run: `.venv/bin/python -m app.cli analyze <id> --amazon-url https://www.amazon.com/dp/B0D1XCVTPB`
Expected: imprime un JSON con `"amazon": {"status": "error", "message": "Falta RAPIDAPI_KEY en .env"}` (porque `.env` aún no tiene la llave real — confirma que el circuito completo funciona sin tronar).

- [ ] **Step 4: Commit**

```bash
git add app/cli.py
git commit -m "feat: agregar comando CLI analyze"
```

---

### Task 9: Dashboard — tarjeta "Datos externos"

**Files:**
- Modify: `dashboard/index.html`

**Interfaces:**
- Consumes: `GET /api/products/{id}` (ahora trae `enrichment`), `POST /api/products/{id}/analyze` (Task 7). Reutiliza `esc()`, `safeUrl()`, `fmt()`, `timeAgo()`, `api()`, y el campo `#f-cost` / `updateMargin()` ya existentes.
- Produces: sección visual "Datos externos" en el panel de detalle, con formulario de dos links y botón para copiar el precio de sourcing al costo de proveedor.

No lleva test automatizado (no hay tooling de pruebas de frontend en este proyecto; el dashboard es un solo HTML servido tal cual). La verificación es manual, en el Step 5, siguiendo la convención del proyecto ("probar escritorio, móvil y modo oscuro").

- [ ] **Step 1: CSS — agregar estilos para el bloque de datos externos**

En `dashboard/index.html`, después de la regla `.margin .good { color: var(--win); } .margin .bad { color: var(--danger); }` (línea 109), agregar:

```css
.ext-block { margin-bottom: 12px; font-size: 14px; }
.ext-block strong { display: block; margin-bottom: 4px; }
.ext-form { margin-top: 12px; }
```

- [ ] **Step 2: Agregar la función `renderExternalData` en el `<script>`**

En `dashboard/index.html`, antes de la función `function renderDetail(p) {` (línea 274), agregar:

```javascript
function renderExternalData(p) {
  const e = p.enrichment;
  const hasAmazon = !!(e && e.amazon_fetched_at);
  const hasSourcing = !!(e && e.sourcing_fetched_at);
  const amazonBlock = hasAmazon ? `<div class="ext-block">
      <strong>Amazon</strong>
      <div class="hint">${e.amazon_rating != null ? `${fmt(e.amazon_rating, 1)} ★ · ` : ""}${e.amazon_reviews_count ?? 0} reseñas${e.amazon_bought_last_month ? ` · ${esc(e.amazon_bought_last_month)}` : ""}</div>
      ${e.amazon_price != null ? `<div class="num">US$${fmt(e.amazon_price, 2)}</div>` : ""}
      ${safeUrl(e.amazon_url) ? `<a class="link" href="${esc(e.amazon_url)}" target="_blank" rel="noopener noreferrer">Ver en Amazon</a>` : ""}
    </div>` : "";
  const sourcingLabel = e && e.sourcing_source === "alibaba" ? "Alibaba" : "AliExpress";
  const sourcingBlock = hasSourcing ? `<div class="ext-block">
      <strong>${sourcingLabel}</strong>
      <div class="hint">${e.sourcing_moq ? `MOQ ${e.sourcing_moq} · ` : ""}${esc(e.sourcing_supplier_name || "")}</div>
      ${e.sourcing_price_unit != null ? `<div class="num">US$${fmt(e.sourcing_price_unit, 2)} <button class="link" type="button" id="use-sourcing-cost">Usar como costo proveedor</button></div>` : ""}
      ${safeUrl(e.sourcing_url) ? `<a class="link" href="${esc(e.sourcing_url)}" target="_blank" rel="noopener noreferrer">Ver publicación</a>` : ""}
    </div>` : "";
  const stamps = [hasAmazon && `Amazon ${timeAgo(e.amazon_fetched_at)}`, hasSourcing && `Sourcing ${timeAgo(e.sourcing_fetched_at)}`]
    .filter(Boolean).join(" · ");
  return `<div class="dsec">
    <h3>Datos externos</h3>
    ${amazonBlock}${sourcingBlock}
    ${stamps ? `<div class="hint">${stamps}</div>` : (hasAmazon || hasSourcing ? "" : `<p class="hint">Pega el link de Amazon y/o de AliExpress o Alibaba para traer números reales de este candidato.</p>`)}
    <button class="btn" type="button" id="btn-analyze" style="margin-top:10px">${hasAmazon || hasSourcing ? "Re-analizar" : "Analizar"}</button>
    <div class="ext-form" id="analyze-form" hidden>
      <div class="fields">
        <label>Link de Amazon<input type="url" id="an-amazon" placeholder="https://amazon.com/..."></label>
        <label>Link de AliExpress o Alibaba<input type="url" id="an-sourcing" placeholder="https://aliexpress.com/..."></label>
      </div>
      <div class="savebar"><button class="btn primary" type="button" id="an-submit">Analizar</button><span id="an-msg" aria-live="polite"></span></div>
    </div>
  </div>`;
}
```

- [ ] **Step 3: Insertar el bloque en `renderDetail` y cablear los eventos**

En `dashboard/index.html`, dentro de `renderDetail(p)`, justo después del cierre del bloque "Números y decisión" (después de `</div>` de la línea 312, antes de la línea `${p.angle || (p.hooks && p.hooks.length) ? ...`), insertar la llamada a `renderExternalData(p)` concatenada al template. Cambiar la línea 312 de:

```javascript
    </div>

    ${p.angle || (p.hooks && p.hooks.length) ? `<div class="dsec">
```

a:

```javascript
    </div>

    ${renderExternalData(p)}

    ${p.angle || (p.hooks && p.hooks.length) ? `<div class="dsec">
```

Después de la línea `updateMargin();` (línea 345, ya existente), agregar el cableado de los nuevos controles:

```javascript
  const useCostBtn = $("use-sourcing-cost");
  if (useCostBtn) useCostBtn.addEventListener("click", () => {
    $("f-cost").value = p.enrichment.sourcing_price_unit;
    updateMargin();
  });
  const analyzeForm = $("analyze-form");
  $("btn-analyze").addEventListener("click", () => { analyzeForm.hidden = !analyzeForm.hidden; });
  $("an-submit").addEventListener("click", async () => {
    const btn = $("an-submit"), msg = $("an-msg");
    const amazonUrl = $("an-amazon").value.trim(), sourcingUrl = $("an-sourcing").value.trim();
    if (!amazonUrl && !sourcingUrl) { msg.textContent = "Pega al menos un link"; msg.style.color = "var(--danger)"; return; }
    btn.disabled = true; msg.textContent = "Analizando..."; msg.style.color = "";
    try {
      const result = await api(`/api/products/${p.id}/analyze`, { method: "POST", body: JSON.stringify({
        amazon_url: amazonUrl || null, sourcing_url: sourcingUrl || null }) });
      const errors = [result.amazon, result.sourcing].filter((r) => r.status === "error").map((r) => r.message);
      if (errors.length) { msg.textContent = errors.join(" · "); msg.style.color = "var(--danger)"; btn.disabled = false; }
      else { await selectProduct(p.id); }
    } catch (err) { msg.textContent = `No se pudo analizar: ${err.message}`; msg.style.color = "var(--danger)"; btn.disabled = false; }
  });
```

- [ ] **Step 4: Sintaxis — validar que el HTML/JS no quedó roto**

Run: `.venv/bin/python -c "import pathlib; pathlib.Path('dashboard/index.html').read_text()"` (chequeo trivial de que el archivo sigue siendo texto válido; el chequeo real es visual en el navegador, Step 5)

También correr `node --check` si hay Node disponible en el sistema, extrayendo el bloque `<script>` a un archivo temporal; si no hay Node instalado, saltar este check y confiar en la verificación manual del Step 5.

- [ ] **Step 5: Verificación manual (obligatoria antes de dar la task por terminada)**

Run: `.venv/bin/python -m app.cli demo && .venv/bin/python -m app.cli serve` y abrir `http://127.0.0.1:8000`.

Checklist:
- Seleccionar un producto candidato (ej. "cepillo quita pelo de mascotas"). Debe aparecer la tarjeta "Datos externos" con el texto de ayuda y el botón "Analizar".
- Click en "Analizar": debe abrir el formulario con los dos campos de link.
- Dejar ambos vacíos y hacer click en "Analizar" (el botón interno del formulario): debe mostrar "Pega al menos un link" sin llamar a la API.
- Pegar un link de Amazon válido (ej. `https://www.amazon.com/dp/B0D1XCVTPB`) sin `RAPIDAPI_KEY` configurada en `.env`: debe mostrar el mensaje de error "Falta RAPIDAPI_KEY en .env" en rojo, sin romper el resto del panel.
- Probar en modo oscuro del sistema operativo y en una ventana angosta (móvil): la tarjeta debe verse consistente con el resto del panel (mismos tokens de color, sin desbordes).
- Confirmar que el resto del panel (score, margen, guardar cambios, anuncios) sigue funcionando igual que antes del cambio.

- [ ] **Step 6: Commit**

```bash
git add dashboard/index.html
git commit -m "feat: agregar tarjeta de datos externos al panel de detalle"
```

---

### Task 10: Documentación y verificación final

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Ninguna (solo documentación).

- [ ] **Step 1: Actualizar `CLAUDE.md`**

En la sección `## Estructura`, después de la línea `services/notify.py     top 3 diario por Telegram` (línea 23 del bloque), agregar:

```
  services/enrichment.py orquesta el analisis on-demand (Amazon + AliExpress/Alibaba) de un candidato
  services/providers/    un modulo por fuente externa: amazon.py, aliexpress.py, alibaba.py, urls.py
```

En la sección `## Próximos pasos (en orden)`, reemplazar la línea `1. Enriquecimiento con AliExpress Affiliate API (búsqueda por imagen -> proveedor y costo automático)` por:

```
1. Enriquecimiento on-demand con Amazon (RapidAPI) y AliExpress/Alibaba: hecho. Falta cargar RAPIDAPI_TOKEN,
   ALIEXPRESS_APP_KEY/APP_SECRET y ALIBABA_APIFY_ACTOR_ID reales en .env para probarlo con datos reales.
```

En la sección `## Comandos`, después de `python -m app.cli top` agregar la línea:

```
python -m app.cli analyze <product_id> --amazon-url URL --sourcing-url URL
```

- [ ] **Step 2: Correr toda la suite una última vez**

Run: `.venv/bin/pytest -q` (o `make test`)
Expected: todos los tests pasan, incluyendo `tests/test_radar.py` y `tests/test_enrichment.py`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: documentar el analizador de producto en CLAUDE.md"
```
