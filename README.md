# Radar de productos ganadores

Detecta productos ganadores para e-commerce contra entrega en República Dominicana a partir de anuncios
de Meta y TikTok. Los agrupa con IA, los puntúa y los muestra en un dashboard de triage diario.

## Arranque rápido

```bash
make setup     # crea .venv, instala dependencias y copia .env.example a .env
make demo      # carga 10 productos de ejemplo
make serve     # abre http://127.0.0.1:8000
```

Para datos reales completa `APIFY_TOKEN` y `ANTHROPIC_API_KEY` en `.env` y sigue la sección
"Primera sesión" de `CLAUDE.md`.

## Cómo se calcula el score

| Señal | Peso | Qué mide |
|---|---|---|
| Longevidad | 35% | Días que un anuncio del producto lleva activo (30+ días = 10) |
| Copias | 25% | Tiendas distintas vendiendo el mismo producto (5+ = 10) |
| Intensidad | 20% | Volumen de anuncios activos y engagement |
| Viabilidad | 20% | Evaluación de Claude, ajustada por tu margen real |

Penalizaciones: tallas x0.6, frágil x0.8, pesado x0.85.

## Operación diaria

```bash
0 6 * * * cd /ruta/radar && .venv/bin/python -m app.cli run pipeline
```

Colecta, normaliza, puntúa y envía el top 3 por Telegram si está configurado.
