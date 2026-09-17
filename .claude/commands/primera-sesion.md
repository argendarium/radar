Ejecuta la checklist "Primera sesión" de CLAUDE.md paso a paso.

Reglas:
- Si falta APIFY_TOKEN o ANTHROPIC_API_KEY en .env, detente y pídemelas. No las escribas en ningún archivo que no sea .env.
- Antes de la primera colecta real, corre `python -m app.cli schema apify/facebook-ads-scraper` y compara con `build_input()` en app/collectors/meta.py. Muéstrame las diferencias antes de cambiar código.
- La primera colecta debe ser barata: solo DO y META_RESULTS_LIMIT=20.
- Después de colectar, inspecciona un registro crudo y confirma que `map_item()` extrae anunciante, texto, imagen y fecha de inicio. Ajusta solo lo necesario.
- Termina con `make test` y un resumen breve de qué funcionó y qué falta.
