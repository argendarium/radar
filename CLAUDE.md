# Radar de productos ganadores

Máquina para detectar productos ganadores para e-commerce contra entrega (COD) en República Dominicana,
usando México y Colombia como señal adelantada. Piloto en RD, luego expansión a otros mercados COD.

## Stack
- Python 3.11+, FastAPI, SQLAlchemy 2 (SQLite hoy, Postgres después vía DATABASE_URL)
- Apify (scrapers administrados) para Meta Ad Library y TikTok Creative Center
- Claude API (Haiku 4.5) para normalizar anuncios con visión y evaluar viabilidad
- Dashboard: un solo HTML en `dashboard/index.html` servido por FastAPI en `/`

## Estructura
```
app/
  config.py              variables de entorno (.env)
  db.py                  modelos: Product, Ad, Run
  mapping.py             extracción tolerante de campos (cada actor nombra distinto)
  collectors/base.py     run_actor() con tope de gasto + upsert_ads()
  collectors/meta.py     Meta Ad Library vía Apify
  collectors/tiktok.py   TikTok Creative Center vía Apify (actor e input configurables)
  services/normalizer.py anuncio -> producto agrupado (Claude visión + texto)
  services/scorer.py     score = 0.35 longevidad + 0.25 copias + 0.20 intensidad + 0.20 viabilidad, con penalizaciones
  services/notify.py     top 3 diario por Telegram
  services/enrichment.py orquesta el análisis on-demand (Amazon + AliExpress/Alibaba) de un candidato
  services/providers/    un modulo por fuente externa: amazon.py, aliexpress.py, alibaba.py, urls.py
  jobs.py                orquestación y registro de ejecuciones (tabla runs)
  api/main.py            API REST + dashboard
  cli.py                 CLI: cada servicio corre por separado
dashboard/index.html     triage diario: ranking, señales, margen, estados, hooks
tests/                   pytest (no requieren llaves)
```

## Comandos
```
make setup        # venv, dependencias, .env, base de datos
make demo         # carga 10 productos demo (marcados is_demo)
make serve        # http://127.0.0.1:8000
make test
python -m app.cli run collect-meta | collect-tiktok | normalize | score | notify | pipeline
python -m app.cli schema <actor_id>    # input schema real de un actor de Apify
python -m app.cli top
python -m app.cli analyze <product_id> --amazon-url URL --sourcing-url URL
```
Sin make: `python -m venv .venv && .venv/bin/pip install -r requirements.txt` y luego `.venv/bin/python -m app.cli ...`

## Hechos que no se deben olvidar
- La API oficial de Meta Ad Library NO devuelve anuncios comerciales fuera de la UE/UK. Por eso usamos Apify sobre la biblioteca pública. No proponer la Graph API para esto.
- Nunca usar cookies ni la cuenta personal de Facebook del usuario en scrapers: arriesga su cuenta publicitaria.
- El input y la salida de cada actor de Apify cambian según el autor. Antes de tocar `build_input()` o `map_item()`, correr `python -m app.cli schema <actor_id>` y revisar una muestra real del dataset.
- `APIFY_MAX_CHARGE_USD` limita el gasto por ejecución. `MAX_NORMALIZE_PER_RUN` limita llamadas a Claude. El presupuesto total del proyecto es pequeño: cuidar costos.
- Un mismo anuncio puede aparecer en varios países: `Ad.country` guarda "DO,MX,CO".
- Tallas, fragilidad y peso penalizan el score porque en contra entrega disparan devoluciones.

## Convenciones
- Interfaz y mensajes al usuario en español, sentence case, sin emojis en ningún lugar (UI, código, commits, logs).
- Diseño: minimalista, moderno, profesional y sobre todo funcional. Mantener los tokens de color y tipografía de `dashboard/index.html`. Probar escritorio, móvil y modo oscuro.
- Diagnosticar primero, luego cambios puntuales. Evitar reescrituras completas de archivos.
- Backend orientado a APIs: cada servicio se puede ejecutar solo (CLI) y por API (`POST /api/jobs/{kind}`), listo para separarse en contenedores.
- Escapar siempre texto scrapeado antes de insertarlo en el HTML.
- Correr `make test` antes de dar un cambio por terminado.

## Primera sesión (hoy)
1. `make setup && make demo && make serve` y abrir http://127.0.0.1:8000
2. Pedir al usuario `APIFY_TOKEN` y `ANTHROPIC_API_KEY` y colocarlos en `.env` (nunca en el código)
3. `python -m app.cli schema apify/facebook-ads-scraper` y ajustar `build_input()` en `collectors/meta.py` si los nombres de campos difieren
4. Prueba barata: `META_COUNTRIES=DO META_RESULTS_LIMIT=20 python -m app.cli run collect-meta`
5. Revisar un item crudo (`SELECT raw FROM ads LIMIT 1`) y ajustar `map_item()` si faltan imagen, texto o fecha
6. `python -m app.cli run normalize` y luego `python -m app.cli run score`
7. Programar cron diario: `0 6 * * * cd /ruta/radar && .venv/bin/python -m app.cli run pipeline`

## Próximos pasos (en orden)
1. Enriquecimiento on-demand con Amazon (RapidAPI) y AliExpress/Alibaba: hecho. Falta cargar RAPIDAPI_KEY,
   ALIEXPRESS_APP_KEY/APP_SECRET, ALIEXPRESS_TRACKING_ID y ALIBABA_APIFY_ACTOR_ID reales en .env para probarlo con datos reales.
2. Postgres + `psycopg[binary]` y docker compose con un contenedor por servicio
3. Aprendizaje: usar resultados de productos en prueba (estado ganador o descartado) para recalibrar pesos del score
4. Análisis de comentarios de anuncios para medir intención de compra

Nota de este proyecto en el vault: 01-proyectos/radar-productos.md
