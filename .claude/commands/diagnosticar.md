Diagnostica este problema del radar sin reescribir archivos completos: $ARGUMENTS

1. Revisa las últimas ejecuciones: `SELECT kind, status, message FROM runs ORDER BY id DESC LIMIT 10` en data/radar.db.
2. Identifica la causa con evidencia (logs, registros crudos, respuesta de la API).
3. Propón el cambio puntual mínimo, aplícalo y corre `make test`.
