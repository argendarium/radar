# Analizador de producto candidato

Fecha: 2026-09-26
Estado: aprobado, listo para plan de implementación

## Problema

Hoy el radar puntúa productos solo con señales de anuncios (longevidad, copias, intensidad, viabilidad estimada
por Claude). Para decidir si un candidato vale la pena probar, el operador sale del dashboard y busca a mano en
Amazon (demanda/prueba social: rating, reseñas, "comprado el mes pasado") y en AliExpress/Alibaba (costo real de
sourcing, MOQ, proveedor). Ese trabajo manual no queda guardado en el radar ni alimenta el cálculo de margen que
ya existe en el panel de detalle.

## Alcance

- On-demand, un producto a la vez. Nunca automático para los 183 productos rastreados (control de costos, mismo
  principio que ya rige Apify: `APIFY_MAX_CHARGE_USD`).
- Dos fuentes nuevas: demanda en Amazon, y costo de sourcing en AliExpress o Alibaba.
- El operador pega el link exacto del producto que ya tiene abierto (no hay búsqueda automática por nombre) —
  evita traer el producto equivocado por una búsqueda por palabras clave ambigua.
- Fuera de alcance por ahora: Google Trends, análisis de comentarios de anuncios, historial de precios,
  reintentos/backoff, caché — YAGNI dado el volumen on-demand bajo.

## Proveedores de datos

| Fuente | Servicio | Costo | Notas |
|---|---|---|---|
| Amazon (demanda) | RapidAPI "Real-Time Amazon Data" | Gratis: 100 requests/mes, sin tarjeta | Consulta por ASIN extraído de la URL pegada |
| AliExpress (sourcing) | API oficial de afiliados (portals.aliexpress.com) | Gratis, aprobación rápida | Ya estaba en el roadmap del proyecto (`CLAUDE.md`, "Próximos pasos") |
| Alibaba (sourcing) | Actor de Apify (scraper de una sola URL) | Pago por resultado, fracciones de centavo | Mismo patrón que colectores Meta/TikTok existentes |

Nuevas variables en `.env` / `app/config.py`: `RAPIDAPI_KEY`, `ALIEXPRESS_APP_KEY`, `ALIEXPRESS_APP_SECRET`,
`ALIEXPRESS_TRACKING_ID`, `ALIBABA_APIFY_ACTOR_ID`, `ALIBABA_MAX_CHARGE_USD` (default bajo, ej. 0.05). Reutiliza
el `APIFY_TOKEN` que ya existe.

## Modelo de datos

Tabla nueva `product_enrichment`, uno a uno con `Product`, se sobrescribe en cada re-análisis (sin histórico):

```
product_id            FK único a products.id
amazon_url             texto, nullable
amazon_price           float, nullable
amazon_rating          float, nullable
amazon_reviews_count   int, nullable
amazon_bought_last_month  texto, nullable   -- ej. "5K+"
amazon_fetched_at      datetime, nullable
sourcing_source        texto, nullable      -- "aliexpress" | "alibaba"
sourcing_url           texto, nullable
sourcing_price_unit    float, nullable
sourcing_moq           int, nullable
sourcing_supplier_name texto, nullable
sourcing_fetched_at    datetime, nullable
raw_amazon              JSON, nullable       -- respuesta cruda, para agregar campos después sin migración
raw_sourcing            JSON, nullable
```

## Componentes

```
app/services/enrichment.py          orquestador: analyze_product(product_id, amazon_url, sourcing_url)
app/services/providers/amazon.py    fetch_amazon_by_url(url) -> AmazonSignal | ProviderError
app/services/providers/aliexpress.py  fetch_sourcing_by_url(url) -> SourcingSignal | ProviderError
app/services/providers/alibaba.py   fetch_sourcing_by_url(url) -> SourcingSignal | ProviderError (vía run_actor())
```

`enrichment.py` decide qué provider llamar según el dominio de cada URL (`amazon.*` / `aliexpress.com` /
`alibaba.com`). Cada provider es independiente: si uno falla, el otro igual se guarda. Nunca todo o nada.

CLI: `python -m app.cli analyze <product_id> --amazon-url ... --sourcing-url ...`, siguiendo la convención de que
cada servicio corre solo por CLI o por API.

## Contrato de API

`POST /api/products/{id}/analyze`

Request:
```json
{"amazon_url": "https://amazon.com/...", "sourcing_url": "https://aliexpress.com/..."}
```
Ambos campos opcionales, pero se exige al menos uno (400 si los dos vienen vacíos).

Response:
```json
{
  "amazon": {"status": "ok", "price": 31.99, "rating": 4.0, "reviews_count": 89,
             "bought_last_month": "5K+", "fetched_at": "2026-09-26T10:00:00Z"},
  "sourcing": {"status": "error", "source": "aliexpress", "message": "Link no reconocido como producto de AliExpress"}
}
```
`status` es `"ok"`, `"error"` o `"skipped"` (cuando no se mandó ese link) por cada fuente, de forma independiente.

Errores por fuente no devuelven 500: el endpoint responde 200 con el detalle de qué fuente sí y cuál no funcionó,
salvo error de validación de la request (400) o producto inexistente (404).

## UI del dashboard

- Tarjeta nueva "Datos externos" en el panel de detalle, debajo del desglose de score.
- Botón "Analizar" abre un mini formulario con los dos campos de link (opcionales, valida que al menos uno esté
  lleno antes de habilitar el botón de enviar).
- Resultado inline: bloque Amazon (rating, # reseñas, "comprado el mes pasado", precio) y bloque Sourcing (precio
  unitario, proveedor, MOQ, badge de fuente, link "ver publicación").
- Botón "Usar como costo proveedor" junto al precio de sourcing: copia el valor al campo `f-cost` existente, que
  ya recalcula margen en vivo (no se toca esa lógica).
- Si ya existe un análisis previo (`*_fetched_at` no nulo), se muestra la fecha y el botón pasa a "Re-analizar",
  para evitar gasto accidental repetido.
- Errores se muestran inline por bloque, en rojo, sin bloquear el bloque que sí funcionó.
- Mismos tokens de color/tipografía que el resto del dashboard (`dashboard/index.html`); sin emojis, español,
  sentence case, como manda `CLAUDE.md`.

## Manejo de errores y costos

- URL de dominio no reconocido → error de validación puntual en ese bloque, no rompe el otro.
- Amazon: si RapidAPI devuelve 429 (cupo mensual agotado) o falta `RAPIDAPI_KEY`, mensaje claro
  "límite mensual de Amazon alcanzado" / "falta configurar la llave de Amazon", sin excepción sin capturar.
- Alibaba: usa el mismo mecanismo de tope de gasto (`run_actor()` con `ALIBABA_MAX_CHARGE_USD`) que ya limita
  Meta/TikTok.
- AliExpress: sin tope de gasto relevante a este volumen (API de afiliados gratuita).
- Sin reintentos automáticos ni caché: si falla, el operador vuelve a pegar el link y reintenta manualmente.

## Pruebas

- Unit tests con pytest, sin llaves reales (como el resto del proyecto): mocks de HTTP por provider, parsing de
  ASIN/ID desde URL, comportamiento de fallo parcial en `enrichment.py`, contrato del endpoint
  (`/api/products/{id}/analyze`) con TestClient de FastAPI.
- Prueba manual antes de dar el feature por terminado: `RAPIDAPI_KEY` real + aprobación de AliExpress afiliados
  en `.env`, reinicio del servicio, análisis real de un candidato con links reales de Amazon y AliExpress,
  confirmar que el dashboard muestra los datos y que "Usar como costo proveedor" llena el margen correctamente.
- `make test` debe pasar antes de considerar el cambio terminado.

## Riesgo y despliegue

Cambio aditivo: tabla nueva, endpoint nuevo, bloque de UI nuevo. No toca `scorer.py`, `normalizer.py` ni los
colectores de Meta/TikTok existentes. Bajo riesgo para el pipeline diario ya en producción. Despliegue: pull +
reinicio del servicio systemd `radar-productos.service`, igual que cualquier otro cambio del repo.
